"""
Inventory services — ORM-based port of the Flask prototype's
modules/inventory.py.

All mutating operations run inside transaction.atomic() to match the
commit-on-success semantics of the Flask version.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q, Sum

from .models import StockItem, StockMovement


VALID_MOVEMENT_TYPES = ('in', 'out', 'adjustment')


# ── Low-stock query ──────────────────────────────────────────────────────────

def get_low_stock_items() -> list:
    """Return items where qty_on_hand <= reorder_point (and reorder > 0)."""
    qs = (StockItem.objects
          .filter(reorder_point__gt=0, qty_on_hand__lte=F('reorder_point'))
          .order_by('-reorder_point'))
    result = []
    for s in qs:
        d = _serialize(s)
        d['qty_shortage'] = float(s.reorder_point) - float(s.qty_on_hand)
        result.append(d)
    return result


# ── Movement history ─────────────────────────────────────────────────────────

def get_movement_history(item_id: int, limit: int = 50) -> list:
    """Return movement history for one stock item, newest first."""
    qs = (StockMovement.objects
          .filter(stock_item_id=item_id)
          .select_related('created_by')
          .order_by('-created_at')[:limit])
    out = []
    for m in qs:
        out.append({
            'id':            m.id,
            'movement_type': m.movement_type,
            'qty':           float(m.qty),
            'ref':           m.ref,
            'reason':        m.reason,
            'user_name':     m.created_by.name if m.created_by else None,
            'created_at':    m.created_at.isoformat(),
        })
    return out


# ── Manual adjustment ────────────────────────────────────────────────────────

@transaction.atomic
def adjust_stock(item_id: int, movement_type: str, qty,
                 reason: str = '', ref: str = '', user_id=None) -> dict:
    """
    Manually adjust stock.

    movement_type:
        'in'         — receiving; adds qty to on-hand
        'out'        — issuing;   subtracts qty (raises if insufficient)
        'adjustment' — correction; sets on-hand to `qty` (absolute)

    Returns the updated stock item as a dict.
    """
    if movement_type not in VALID_MOVEMENT_TYPES:
        raise ValueError(f'movement_type must be one of {VALID_MOVEMENT_TYPES}')

    try:
        qty = Decimal(str(qty))
    except (ArithmeticError, ValueError):
        raise ValueError('qty must be numeric')
    if qty <= 0:
        raise ValueError('qty must be greater than 0')

    item = StockItem.objects.select_for_update().filter(pk=item_id).first()
    if not item:
        raise ValueError(f'Stock item {item_id} not found')

    current = Decimal(item.qty_on_hand)

    if movement_type == 'in':
        new_qty = current + qty
    elif movement_type == 'out':
        if qty > current:
            raise ValueError(
                f'Cannot remove {qty} — only {current} in stock.'
            )
        new_qty = current - qty
    else:  # 'adjustment' — absolute
        new_qty = qty

    item.qty_on_hand = new_qty
    item.save(update_fields=['qty_on_hand', 'updated_at'])

    StockMovement.objects.create(
        stock_item    = item,
        movement_type = movement_type,
        qty           = qty,
        ref           = ref or '',
        reason        = reason or '',
        created_by_id = user_id,
    )

    return _serialize(item)


# ── Auto-deduct on delivery ──────────────────────────────────────────────────

@transaction.atomic
def deduct_stock_on_delivery(delivery_note_id: int, user_id=None) -> list:
    """
    Called when a delivery note is confirmed.
    Fuzzy-matches delivery note items to stock items by description
    (case-insensitive, first-40-chars), then deducts qty_delivered.

    Returns a list of per-item result dicts.
    """
    from apps.documents.models import DeliveryNoteItem

    rows = (DeliveryNoteItem.objects
            .filter(delivery_note_id=delivery_note_id)
            .select_related('deal_item'))

    results = []
    for dni in rows:
        di = dni.deal_item
        result = {
            'deal_item_id':  di.id if di else None,
            'description':   di.description if di else '',
            'qty_delivered': float(dni.qty_delivered),
            'stock_item_id': None,
            'matched':       False,
            'deducted':      False,
            'message':       '',
        }
        if not di:
            results.append(result); continue

        search = (di.description or '')[:40]
        stock = StockItem.objects.filter(description__icontains=search).first()
        if not stock:
            result['message'] = 'No matching stock item found — skipped'
            results.append(result); continue

        result['stock_item_id'] = stock.id
        result['matched']       = True

        qty_to_deduct = Decimal(dni.qty_delivered)
        current_stock = Decimal(stock.qty_on_hand)

        if qty_to_deduct > current_stock:
            result['message'] = (
                f'Insufficient stock: has {current_stock}, '
                f'need {qty_to_deduct} — deducted to 0'
            )
            qty_to_deduct = current_stock

        stock.qty_on_hand = current_stock - qty_to_deduct
        stock.save(update_fields=['qty_on_hand', 'updated_at'])

        StockMovement.objects.create(
            stock_item    = stock,
            movement_type = 'out',
            qty           = qty_to_deduct,
            ref           = f'DN-{delivery_note_id}',
            reason        = f'Delivery note #{delivery_note_id}',
            created_by_id = user_id,
        )

        result['deducted'] = True
        if not result['message']:
            result['message'] = f"Deducted {qty_to_deduct} from '{stock.description}'"
        results.append(result)

    return results


# ── Summary ──────────────────────────────────────────────────────────────────

def get_stock_summary() -> dict:
    """Aggregate stats for the inventory dashboard header."""
    agg = StockItem.objects.aggregate(
        total_items         = Count('id'),
        low_stock_count     = Count('id', filter=Q(qty_on_hand__lte=F('reorder_point'),
                                                   reorder_point__gt=0)),
        out_of_stock_count  = Count('id', filter=Q(qty_on_hand=0)),
        total_units         = Sum('qty_on_hand'),
    )
    return {
        'total_items':        int(agg['total_items'] or 0),
        'low_stock_count':    int(agg['low_stock_count'] or 0),
        'out_of_stock_count': int(agg['out_of_stock_count'] or 0),
        'total_units':        float(agg['total_units'] or 0),
    }


# ── helpers ──────────────────────────────────────────────────────────────────

def _serialize(s: StockItem) -> dict:
    return {
        'id':            s.id,
        'sku':           s.sku,
        'description':   s.description,
        'unit':          s.unit,
        'qty_on_hand':   float(s.qty_on_hand),
        'qty_reserved':  float(s.qty_reserved),
        'qty_available': s.qty_available,
        'reorder_point': float(s.reorder_point),
        'is_low_stock':  s.is_low_stock,
        'updated_at':    s.updated_at.isoformat() if s.updated_at else None,
    }

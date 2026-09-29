"""
Service layer for deals — split/award logic ported from
the Flask prototype's modules/database.py.
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum

from .models import Deal, DealItem, DealItemSplit


@transaction.atomic
def split_item_to_supplier(parent_item_id: int,
                           supplier_quote_id: int,
                           qty_awarded,
                           unit_cost) -> dict:
    """
    Award `qty_awarded` units of a parent DealItem to a specific supplier quote.

    Creates (or updates) a child DealItem row for the awarded portion,
    plus a DealItemSplit record. Caps qty_awarded at the remaining
    un-awarded quantity, returning a warning if capping occurred.

    Returns:
        {'child_item_id': int, 'warning': str | None}
    """
    from apps.quotes.models import SupplierQuote  # local import to avoid cycles

    parent = DealItem.objects.select_related('deal').filter(pk=parent_item_id).first()
    if not parent:
        raise ValueError(f'Item {parent_item_id} not found')

    try:
        qty_awarded = Decimal(str(qty_awarded))
        unit_cost   = Decimal(str(unit_cost))
    except (ArithmeticError, ValueError):
        raise ValueError('qty_awarded and unit_cost must be numeric')

    parent_qty = Decimal(parent.qty)
    unit_price = Decimal(parent.unit_price or 0)
    margin_pct = (
        round((unit_price - unit_cost) / unit_price, 6)
        if unit_price > 0 else Decimal('0')
    )

    # Cap at remaining quantity (excluding this supplier's existing share)
    already = DealItemSplit.objects.filter(
        parent_item_id=parent_item_id,
    ).exclude(supplier_quote_id=supplier_quote_id).aggregate(
        already_awarded=Sum('qty_awarded')
    )['already_awarded'] or Decimal('0')

    remaining = parent_qty - Decimal(already)
    warning = None
    if qty_awarded > remaining:
        warning = (
            f'Qty {qty_awarded} exceeds remaining {remaining} — capped'
        )
        qty_awarded = remaining

    # Upsert the split row
    existing_split = DealItemSplit.objects.filter(
        parent_item_id=parent_item_id,
        supplier_quote_id=supplier_quote_id,
    ).first()

    if existing_split:
        existing_split.qty_awarded = qty_awarded
        existing_split.unit_cost   = unit_cost
        existing_split.save(update_fields=['qty_awarded', 'unit_cost'])

        child = existing_split.child_item
        if child:
            child.qty        = qty_awarded
            child.unit_cost  = unit_cost
            child.margin_pct = margin_pct
            child.save(update_fields=['qty', 'unit_cost', 'margin_pct'])
        child_item_id = child.id if child else None

    else:
        # Create the child DealItem
        child = DealItem.objects.create(
            deal=parent.deal,
            item_number=parent.item_number,
            description=parent.description,
            part_number=parent.part_number or '',
            brand=parent.brand or '',
            model_name=parent.model_name or '',
            qty=qty_awarded,
            unit=parent.unit or '',
            unit_cost=unit_cost,
            margin_pct=margin_pct,
            unit_price=unit_price,
            parent_item=parent,
            awarded_quote_id=supplier_quote_id,
            is_split_child=True,
        )
        DealItemSplit.objects.create(
            parent_item_id=parent_item_id,
            supplier_quote_id=supplier_quote_id,
            qty_awarded=qty_awarded,
            unit_cost=unit_cost,
            child_item=child,
        )
        child_item_id = child.id

    return {'child_item_id': child_item_id, 'warning': warning}


@transaction.atomic
def remove_item_split(parent_item_id: int, supplier_quote_id: int) -> bool:
    """
    Remove the split/award for one supplier from a parent item.
    Deletes both the split row and the child DealItem.
    Returns True if something was removed.
    """
    split = DealItemSplit.objects.filter(
        parent_item_id=parent_item_id,
        supplier_quote_id=supplier_quote_id,
    ).first()
    if not split:
        return False
    if split.child_item_id:
        DealItem.objects.filter(pk=split.child_item_id).delete()
    split.delete()
    return True


@transaction.atomic
def upsert_quote_item(quote_id: int, deal_item_id: int, unit_price) -> int:
    """
    INSERT-OR-UPDATE a supplier quote line. Returns the row id.
    """
    from apps.quotes.models import SupplierQuoteItem

    item = DealItem.objects.filter(pk=deal_item_id).first()
    qty  = Decimal(item.qty) if item else Decimal('1')
    try:
        up = Decimal(str(unit_price or 0))
    except (ArithmeticError, ValueError):
        up = Decimal('0')
    total_price = round(up * qty, 4)

    qi, _ = SupplierQuoteItem.objects.update_or_create(
        quote_id=quote_id, deal_item_id=deal_item_id,
        defaults={'unit_price': up, 'total_price': total_price},
    )
    return qi.id


@transaction.atomic
def apply_winning_quote(deal_id: int, quote_id: int) -> int:
    """
    Mark `quote_id` as the winner for a deal, push its supplier prices
    onto the parent deal_items.unit_cost, and recompute margin_pct.
    Returns the number of items updated.
    """
    from apps.quotes.models import SupplierQuote, SupplierQuoteItem

    # Un-select any existing winner for this deal, then select this one
    SupplierQuote.objects.filter(deal_id=deal_id).update(selected=False)
    SupplierQuote.objects.filter(pk=quote_id, deal_id=deal_id).update(selected=True)

    quote_items = SupplierQuoteItem.objects.filter(quote_id=quote_id)
    updated = 0
    for qi in quote_items:
        item = DealItem.objects.filter(pk=qi.deal_item_id).first()
        if not item or item.is_split_child:
            continue
        item.unit_cost = qi.unit_price
        if item.unit_price and item.unit_price > 0:
            item.margin_pct = (Decimal(item.unit_price) - Decimal(qi.unit_price)) \
                              / Decimal(item.unit_price)
        item.save(update_fields=['unit_cost', 'margin_pct'])
        updated += 1
    return updated



def annotate_list_summary(qs):
    """
    Add what the deals list shows at a glance: sell value, cost, number of
    lines, supplier orders received out of total, and the next shipment ETA.
    Order and shipment figures use subqueries so the item sums aren't multiplied.
    """
    from django.db.models import Count, F, OuterRef, Q, Subquery, Sum
    from apps.logistics.models import Shipment, SupplierOrder

    top_level = Q(items__is_split_child=False)
    live_orders = SupplierOrder.objects.filter(deal=OuterRef('pk')).exclude(status='cancelled')
    return qs.annotate(
        sum_price=Sum(F('items__qty') * F('items__unit_price'), filter=top_level),
        sum_cost=Sum(F('items__qty') * F('items__unit_cost'), filter=top_level),
        item_count=Count('items', filter=top_level),
        orders_total=Subquery(live_orders.values('deal').annotate(n=Count('id')).values('n')[:1]),
        orders_received=Subquery(live_orders.filter(status='received')
                                 .values('deal').annotate(n=Count('id')).values('n')[:1]),
        next_eta=Subquery(Shipment.objects.filter(deal=OuterRef('pk'), status__in=Shipment.OPEN_STATUSES,
                                                  eta__isnull=False).order_by('eta').values('eta')[:1]),
    )

"""
Business rules for supplier orders and shipments:
  - which awarded quantities are not yet on a supplier order
  - creating orders from awards
  - status changes (date stamps, knock-on updates, activity log)
  - the tracking board and "needs attention" reminders
"""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.deals.models import Deal, DealActivity, DealItem, DealItemSplit
from .models import Shipment, SupplierOrder, SupplierOrderItem

# Reminder thresholds, in days.
DRAFT_NOT_SENT_DAYS     = 2
NO_CONFIRMATION_DAYS    = 3
READY_NOT_SHIPPED_DAYS  = 2
SHIPMENT_STALE_DAYS     = 7

# Deal stages where the client has committed and we should be ordering.
ORDERING_STAGES = ("Client's PO Received", 'PO Sent')


def log(deal, user, text, kind='logistics'):
    DealActivity.objects.create(deal=deal, user=user if getattr(user, 'is_authenticated', False) else None,
                                activity_type=kind, description=text)


# ── Awards not yet ordered ──────────────────────────────────────────────────
def pending_awards(deal):
    """
    Awarded quantities that are not on a (non-cancelled) supplier order yet.
    Returns a list of dicts, one per (line item, supplier quote).
    """
    awarded = {}   # (item_id, quote_id) → {qty, unit_cost, item, quote}
    splits = (DealItemSplit.objects
              .filter(parent_item__deal=deal)
              .select_related('parent_item', 'supplier_quote', 'supplier_quote__supplier'))
    for s in splits:
        awarded[(s.parent_item_id, s.supplier_quote_id)] = {
            'qty': s.qty_awarded, 'unit_cost': s.unit_cost, 'item': s.parent_item, 'quote': s.supplier_quote,
        }
    # Items awarded whole without a split record.
    split_items = {k[0] for k in awarded}
    for it in (DealItem.objects.filter(deal=deal, is_split_child=False, awarded_quote__isnull=False)
               .exclude(id__in=split_items).select_related('awarded_quote', 'awarded_quote__supplier')):
        awarded[(it.id, it.awarded_quote_id)] = {
            'qty': it.qty, 'unit_cost': it.unit_cost, 'item': it, 'quote': it.awarded_quote,
        }

    ordered = defaultdict(Decimal)
    for line in (SupplierOrderItem.objects
                 .filter(order__deal=deal, deal_item__isnull=False)
                 .exclude(order__status='cancelled')
                 .select_related('order')):
        ordered[(line.deal_item_id, line.order.supplier_quote_id)] += line.qty

    out = []
    for (item_id, quote_id), a in awarded.items():
        remaining = a['qty'] - ordered.get((item_id, quote_id), Decimal(0))
        if remaining <= 0:
            continue
        quote = a['quote']
        out.append({
            'deal_item_id':      item_id,
            'item_number':       a['item'].item_number,
            'description':       a['item'].description,
            'supplier_quote_id': quote_id,
            'supplier_id':       quote.supplier_id if quote else None,
            'supplier_name':     quote.supplier.company_name if quote and quote.supplier else 'Unknown supplier',
            'qty_pending':       _qty_str(remaining),
            'unit':              a['item'].unit,
            'unit_cost':         str(a['unit_cost']),
        })
    out.sort(key=lambda r: (r['supplier_name'], r['item_number']))
    return out


def _qty_str(d):
    """Decimal → plain string without trailing zeros or exponent (10.0000 → '10')."""
    if d == d.to_integral():
        return str(d.quantize(Decimal(1)))
    return format(d.normalize(), 'f')


def _next_po_number(deal):
    base = deal.reference or f'D{deal.pk}'
    n = SupplierOrder.objects.filter(deal=deal).count() + 1
    while SupplierOrder.objects.filter(po_number=f'{base}-P{n}').exists():
        n += 1
    return f'{base}-P{n}'


@transaction.atomic
def create_orders_from_awards(deal, user):
    """
    Put every pending award on a supplier order: one order per supplier quote.
    Adds to an existing draft order for that quote if there is one.
    Returns the list of orders created or extended.
    """
    by_quote = defaultdict(list)
    for p in pending_awards(deal):
        by_quote[p['supplier_quote_id']].append(p)

    touched = []
    for quote_id, lines in by_quote.items():
        order = (SupplierOrder.objects.filter(deal=deal, supplier_quote_id=quote_id, status='draft')
                 .order_by('id').first())
        created = False
        if not order:
            from apps.quotes.models import SupplierQuote
            q = SupplierQuote.objects.filter(pk=quote_id).select_related('supplier').first()
            order = SupplierOrder.objects.create(
                deal=deal,
                supplier=q.supplier if q else None,
                supplier_quote=q,
                po_number=_next_po_number(deal),
                currency=deal.currency,
                payment_terms=(q.payment_terms if q else '') or '',
                incoterm=(q.incoterm if q else '') or '',
                created_by=user if getattr(user, 'is_authenticated', False) else None,
            )
            created = True
        for p in lines:
            item = DealItem.objects.get(pk=p['deal_item_id'])
            qty = Decimal(p['qty_pending'])
            existing = order.items.filter(deal_item=item).first()
            if existing:
                existing.qty += qty
                existing.save(update_fields=['qty'])
            else:
                SupplierOrderItem.objects.create(
                    order=order, deal_item=item, item_number=item.item_number,
                    description=item.description, part_number=item.part_number, brand=item.brand,
                    qty=qty, unit=item.unit, unit_cost=Decimal(p['unit_cost']),
                )
        supplier = order.supplier.company_name if order.supplier else 'supplier'
        log(deal, user, f'Supplier order {order.po_number} {"created" if created else "updated"} '
                        f'for {supplier} ({len(lines)} line(s)).')
        touched.append(order)
    return touched


# ── Status changes ──────────────────────────────────────────────────────────
def stamp_order_status(order, old_status):
    """Fill in the date for the order's new status, if not already set."""
    field = SupplierOrder.STATUS_DATE_FIELD.get(order.status)
    if field and not getattr(order, field):
        setattr(order, field, timezone.localdate())


def after_shipment_change(shipment, old_status, user):
    """
    Keep supplier orders in step with their shipment:
      - a shipment leaving marks its orders as shipped
      - a first-leg shipment arriving (to Miami, or direct) marks them received
    """
    today = timezone.localdate()
    if shipment.status == 'in_transit' and not shipment.departed_date:
        shipment.departed_date = today
    if shipment.status == 'arrived' and not shipment.arrived_date:
        shipment.arrived_date = today

    changed = []
    for order in shipment.orders.all():
        new = None
        if shipment.status in ('in_transit', 'customs', 'arrived') and order.status in ('draft', 'sent', 'confirmed', 'ready'):
            new = 'shipped'
        if shipment.status == 'arrived' and shipment.leg in ('to_miami', 'direct') and order.status != 'cancelled':
            new = 'received'
        if new and new != order.status:
            prev = order.status
            order.status = new
            stamp_order_status(order, prev)
            if new == 'received' and not order.shipped_date:
                order.shipped_date = shipment.departed_date or today
            order.save()
            changed.append(f'{order.po_number} → {order.get_status_display().lower()}')
    if changed:
        log(shipment.deal, user, 'Updated from shipment: ' + ', '.join(changed) + '.')


# ── Tracking board ──────────────────────────────────────────────────────────
def _days(a, b):
    return (a - b).days


def _n_days(n):
    return f'{n} day' if n == 1 else f'{n} days'


def _order_entry(o, today):
    flags = []
    open_ship = [s for s in o.shipments.all() if s.status != 'cancelled']
    if o.status == 'draft':
        age = _days(today, timezone.localtime(o.created_at).date())
        if age >= DRAFT_NOT_SENT_DAYS:
            flags.append(('warn', f'Not sent to the supplier yet ({_n_days(age)} since created)'))
    if o.status == 'sent' and o.sent_date:
        waited = _days(today, o.sent_date)
        if waited >= NO_CONFIRMATION_DAYS:
            flags.append(('warn', f'No confirmation from the supplier after {_n_days(waited)}'))
    if o.status in ('draft', 'sent', 'confirmed') and o.promised_date and o.promised_date < today:
        flags.append(('late', f'{_n_days(_days(today, o.promised_date))} past the promised date'))
    if o.status == 'ready' and not open_ship:
        since = o.ready_date or today
        if _days(today, since) >= READY_NOT_SHIPPED_DAYS:
            flags.append(('warn', f'Ready for {_n_days(_days(today, since))}, no shipment arranged'))
    if o.status == 'shipped' and not open_ship:
        flags.append(('warn', 'Marked shipped, but no shipment or tracking recorded'))

    due = None
    if o.status in ('draft', 'sent', 'confirmed'):
        due = o.promised_date
    elif o.status in ('ready', 'shipped'):
        etas = [s.eta for s in open_ship if s.eta and s.status in Shipment.OPEN_STATUSES]
        due = min(etas) if etas else o.ready_date

    return {
        'kind': 'order', 'id': o.id,
        'deal_id': o.deal_id, 'deal_reference': o.deal.reference, 'client_name': o.deal.client.dropdown_name,
        'title': f'{o.po_number}, {o.supplier.company_name if o.supplier else "no supplier"}',
        'subtitle': f'{o.items.count()} line(s)' + (f', supplier ref {o.supplier_ref}' if o.supplier_ref else ''),
        'status': o.status, 'status_label': o.get_status_display(),
        'due_date': due, 'flags': [{'level': l, 'text': t} for l, t in flags],
    }


def _shipment_entry(s, today):
    flags = []
    if s.status in ('planned', 'booked') and s.etd and s.etd < today and not s.departed_date:
        flags.append(('warn', f'Was due to leave on {s.etd:%b %d}'))
    if s.eta and s.eta < today:
        flags.append(('late', f'{_n_days(_days(today, s.eta))} past the ETA'))
    if s.status in ('in_transit', 'customs'):
        last = timezone.localtime(s.last_update_at or s.created_at).date()
        quiet = _days(today, last)
        if quiet >= SHIPMENT_STALE_DAYS:
            flags.append(('warn', f'No update in {_n_days(quiet)}'))
        if not s.tracking_number:
            flags.append(('warn', 'No tracking number'))

    route = ' to '.join(x for x in (s.origin, s.destination) if x)
    return {
        'kind': 'shipment', 'id': s.id,
        'deal_id': s.deal_id, 'deal_reference': s.deal.reference, 'client_name': s.deal.client.dropdown_name,
        'title': f'{s.get_leg_display()}, {s.get_mode_display().lower()}'
                 + (f', {s.forwarder}' if s.forwarder else ''),
        'subtitle': ', '.join(x for x in (route, s.tracking_number and f'tracking {s.tracking_number}') if x),
        'status': s.status, 'status_label': s.get_status_display(),
        'due_date': s.eta or s.etd, 'flags': [{'level': l, 'text': t} for l, t in flags],
    }


def _deal_entries(deals_qs, today):
    out = []
    for d in deals_qs.filter(status__in=ORDERING_STAGES).select_related('client'):
        pend = pending_awards(d)
        has_awards = DealItemSplit.objects.filter(parent_item__deal=d).exists() or \
            DealItem.objects.filter(deal=d, awarded_quote__isnull=False).exists()
        if pend:
            text = f'{len(pend)} awarded line(s) not on a supplier order yet'
        elif not has_awards and d.items.filter(is_split_child=False).exists():
            text = "Client's PO received, but no items awarded to suppliers yet"
        else:
            continue
        out.append({
            'kind': 'deal', 'id': d.id,
            'deal_id': d.id, 'deal_reference': d.reference, 'client_name': d.client.dropdown_name,
            'title': 'Supplier orders to place', 'subtitle': f'Stage: {d.status}',
            'status': 'to_order', 'status_label': 'To order',
            'due_date': None, 'flags': [{'level': 'warn', 'text': text}],
        })
    return out


def build_board(user):
    today = timezone.localdate()
    deals = Deal.objects.all()
    if getattr(user, 'role', None) == 'sales':
        deals = deals.filter(owner=user)

    orders = (SupplierOrder.objects.filter(deal__in=deals, status__in=SupplierOrder.OPEN_STATUSES)
              .select_related('deal', 'deal__client', 'supplier').prefetch_related('shipments', 'items'))
    ships = (Shipment.objects.filter(deal__in=deals, status__in=Shipment.OPEN_STATUSES)
             .select_related('deal', 'deal__client'))

    entries = [_order_entry(o, today) for o in orders]
    # A shipped order is followed through its shipment; only list it if something is off.
    entries = [e for e in entries if e['status'] != 'shipped' or e['flags']]
    entries += [_shipment_entry(s, today) for s in ships]
    entries += _deal_entries(deals, today)

    def sort_key(e):
        severity = 0 if any(f['level'] == 'late' for f in e['flags']) else (1 if e['flags'] else 2)
        return (severity, e['due_date'] is None, e['due_date'] or today, e['deal_reference'] or '')
    entries.sort(key=sort_key)
    for e in entries:
        e['due_date'] = e['due_date'].isoformat() if e['due_date'] else None
    return {'today': today.isoformat(), 'entries': entries}

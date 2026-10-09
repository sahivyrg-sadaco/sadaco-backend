"""
Payment gates: steps that must wait for money.

Supplier side (per supplier order)
  Shipping (order → shipped, or a shipment carrying it departing) needs:
    - the supplier's invoice recorded, when the terms have anything due before shipping
    - every "on order" and "before shipping" share of that invoice paid
    - a tracking / AWB / BL number (courier, air and ocean)
Client side (per deal)
  Sending a supplier order needs the client's "on order" share received.
  A shipment to the client departing needs the "on order" and "before
  shipping" shares received.

Blocked actions answer 409 with what's missing. An admin can pass
`override_reason` to go ahead anyway; the override is logged on the deal.
"""
from rest_framework import status
from rest_framework.response import Response

from apps.deals.models import DealActivity
from apps.payments.models import Payment
from . import plans
from .models import ClientInvoice

SHIPPED_STATUSES = ('shipped', 'received')
DEPARTED = ('in_transit', 'customs', 'arrived')
TRACKED_MODES = ('courier', 'air', 'ocean')
TO_CLIENT_LEGS = ('export', 'delivery', 'direct')
OVERRIDE_MIN_CHARS = 5


def _m(currency, v):
    return f'{currency} {v:,.2f}'


# ── Status of each side ─────────────────────────────────────────────────────
def order_money(order):
    """Where a supplier order stands against its payment terms."""
    steps, source = plans.for_order(order)
    # .all() uses rows already loaded by prefetch_related('payables__payments') when present.
    payables = [p for p in order.payables.all() if p.kind == 'goods']
    total = sum(float(p.amount) for p in payables)
    paid = sum(float(x.amount) for p in payables for x in p.payments.all())
    pre = plans.pre_shipping_pct(steps)
    required = round(total * pre / 100, 2)
    supplier = order.supplier.company_name if order.supplier else 'the supplier'
    text = plans.describe(steps)
    missing = None
    if pre > 0 and not payables:
        missing = f"Record {supplier}'s invoice first. Their terms ({text}) need payment before shipping."
    elif pre > 0 and paid < required - 0.01:
        missing = (f'Pay {_m(order.currency, required - paid)} more to {supplier} first. '
                   f'Their terms ({text}) need {pre:g}% paid before shipping; paid so far: {_m(order.currency, paid)}.')
    return {
        'steps': steps, 'plan_text': text, 'plan_text_es': plans.describe_es(steps), 'source': source,
        'invoiced': bool(payables), 'invoice_total': round(total, 2), 'paid': round(paid, 2),
        'pre_shipping_pct': pre, 'required_before_shipping': required,
        'ready_to_ship': missing is None, 'missing': missing, 'currency': order.currency,
    }


def client_money(deal):
    """Where the client stands against the deal's terms: advance and before-shipping shares."""
    from .services import billing_base
    steps, source = plans.for_deal(deal)
    revenue, revenue_source = billing_base(deal)
    numbers = ClientInvoice.objects.filter(deal=deal, cancelled=False).values_list('number', flat=True)
    received = float(sum(p.amount for p in Payment.objects.filter(invoice_ref__in=list(numbers), deal=deal)))
    adv_pct, pre_pct = plans.on_order_pct(steps), plans.pre_shipping_pct(steps)
    adv_req, pre_req = round(revenue * adv_pct / 100, 2), round(revenue * pre_pct / 100, 2)
    text = plans.describe(steps)
    cur = deal.currency
    return {
        'steps': steps, 'plan_text': text, 'plan_text_es': plans.describe_es(steps), 'source': source, 'revenue': round(revenue, 2),
        'revenue_source': revenue_source,
        'received': round(received, 2), 'currency': cur,
        'advance_pct': adv_pct, 'advance_required': adv_req,
        'advance_met': received >= adv_req - 0.01,
        'advance_missing': None if received >= adv_req - 0.01 else
            f"Receive the client's payment due on order first: {_m(cur, adv_req - received)} still due. "
            f'Terms: {text}. Received so far: {_m(cur, received)}.',
        'before_shipping_required': pre_req,
        'before_shipping_met': received >= pre_req - 0.01,
        'before_shipping_missing': None if received >= pre_req - 0.01 else
            f'Receive {_m(cur, pre_req - received)} more from the client before shipping to them. '
            f'Terms ({text}) need {pre_pct:g}% paid by shipping; received so far: {_m(cur, received)}.',
    }


# ── Checks for specific actions ─────────────────────────────────────────────
def for_creating_orders(deal):
    """
    Gates for creating (or sending) supplier orders: the client's PO must be
    processed, and the share of the deal the terms put "on order" received.
    """
    from apps.clientquotes.services import po_status
    s = po_status(deal)
    if not s['processed']:
        return [{'code': 'client_po', 'message': s['message']}]
    c = client_money(deal)
    return [] if c['advance_met'] else [{'code': 'client_advance', 'message': c['advance_missing']}]


def for_client_invoice(deal):
    """Client invoices are issued against the client's processed PO."""
    from apps.clientquotes.services import po_status
    s = po_status(deal)
    return [] if s['processed'] else [{'code': 'client_po', 'message':
            "Record and process the client's purchase order before invoicing them."}]


def for_order_status(order, new_status):
    """Gates for changing a supplier order's status by hand."""
    out = []
    old = order.status
    if old == 'draft' and new_status not in ('draft', 'cancelled'):
        out += for_creating_orders(order.deal)
    if new_status in SHIPPED_STATUSES and old not in SHIPPED_STATUSES:
        m = order_money(order)
        if m['missing']:
            out.append({'code': 'supplier_payment', 'message': m['missing']})
        tracked = [s for s in order.shipments.exclude(status='cancelled') if s.tracking_number]
        if not tracked:
            out.append({'code': 'tracking', 'message':
                        f'{order.po_number} has no shipment with a tracking number. Add the shipment '
                        '(with the tracking, AWB or BL number the supplier sent) instead of marking it shipped by hand.'})
    return out


def for_shipment(deal, *, old_status, new_status, mode, tracking, leg, orders):
    """Gates for a shipment being created or updated."""
    out = []
    departing = new_status in DEPARTED and (old_status not in DEPARTED)
    if departing and mode in TRACKED_MODES and not (tracking or '').strip():
        out.append({'code': 'tracking', 'message':
                    'Enter the tracking, AWB or BL number before marking the shipment as departed.'})
    moving = [o for o in orders if o.status not in SHIPPED_STATUSES and o.status != 'cancelled']
    if new_status in DEPARTED:
        for o in moving:
            m = order_money(o)
            if m['missing']:
                out.append({'code': 'supplier_payment', 'message': f'{o.po_number}: {m["missing"]}'})
    if departing and leg in TO_CLIENT_LEGS:
        c = client_money(deal)
        if c['before_shipping_missing']:
            out.append({'code': 'client_payment', 'message': c['before_shipping_missing']})
    return out


def enforce(request, deal, gates):
    """None if the action may go ahead (no gates, or a valid admin override); else a 409 response."""
    if not gates:
        return None
    reason = str(request.data.get('override_reason') or '').strip()
    is_admin = getattr(request.user, 'role', None) == 'admin'
    if reason and is_admin and len(reason) >= OVERRIDE_MIN_CHARS:
        for g in gates:
            DealActivity.objects.create(
                deal=deal, user=request.user, activity_type='override',
                description=f'Payment rule overridden by {request.user.name}: {g["message"]} Reason: {reason}')
        return None
    if reason and not is_admin:
        msg = 'Only an admin can override payment rules.'
    elif reason:
        msg = f'Give a reason of at least {OVERRIDE_MIN_CHARS} characters.'
    else:
        msg = gates[0]['message']
    return Response({'error': msg, 'gates': gates, 'can_override': is_admin},
                    status=status.HTTP_409_CONFLICT)

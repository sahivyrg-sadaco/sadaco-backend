"""
Deal stages that follow from what has happened (forward only, never back):

  PO Sent    every won line is on a supplier order, and no order is still a draft
  Invoiced   the client has been invoiced for the whole PO
  Delivered  a shipment to the client (port-to-client or direct) has arrived
  Closed     delivered, the client has paid in full, and every supplier and cost bill is paid

"Negotiating" (quote sent) and "Client's PO Received" (PO processed) are set where those happen.
"""
from apps.clientquotes.services import STAGE_ORDER, advance_stage


def _po_sent(deal):
    from apps.clientquotes.services import po_status
    from apps.logistics.models import SupplierOrder
    from apps.logistics.services import pending_awards
    if not po_status(deal)['processed']:
        return False
    orders = list(SupplierOrder.objects.filter(deal=deal).exclude(status='cancelled'))
    return bool(orders) and all(o.status != 'draft' for o in orders) and not pending_awards(deal)


def _invoiced(deal):
    from .models import ClientInvoice
    from .services import billing_base
    base, _ = billing_base(deal)
    total = sum(float(i.amount) for i in ClientInvoice.objects.filter(deal=deal, cancelled=False))
    return base > 0 and total >= base - 0.01


def _delivered(deal):
    from apps.logistics.models import Shipment
    return Shipment.objects.filter(deal=deal, leg__in=('delivery', 'direct'), status='arrived').exists()


def _closed(deal):
    from .services import deal_money
    if not (_delivered(deal) and _invoiced(deal)):
        return False
    m = deal_money(deal)
    return m['client']['to_collect'] <= 0.01 and all(p['status'] == 'paid' for p in m['payables'])


CHECKS = [('PO Sent', _po_sent), ('Invoiced', _invoiced), ('Delivered', _delivered), ('Closed', _closed)]


def sync(deal, user=None):
    """Move the deal to the furthest stage its facts support. Never raises."""
    try:
        deal.refresh_from_db(fields=['status'])
        if deal.status not in STAGE_ORDER:      # e.g. Cancelled: leave alone
            return
        reached = None
        for stage, check in CHECKS:
            if check(deal):
                reached = stage
        if reached:
            advance_stage(deal, reached, user)
    except Exception:  # a stage hint must never break the action that triggered it
        pass

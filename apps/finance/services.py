"""
Receivables, payables and per-deal cash position.

Status rules (both directions)
- paid:    balance ≤ 0.005
- partial: something paid, balance left
- open:    nothing paid
Overdue = not paid and due date before today.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.deals.models import Deal, DealActivity
from apps.payments.models import Payment
from apps.payments.services import parse_payment_terms_days
from .models import ClientInvoice, Payable, PayablePayment

DUE_SOON_DAYS = 3


def log(deal, user, text):
    DealActivity.objects.create(deal=deal, user=user if getattr(user, 'is_authenticated', False) else None,
                                activity_type='payment', description=text)


def terms_due_date(invoice_date, terms):
    """Due date from payment terms. Advance / prepaid / on-delivery terms are due on the invoice date."""
    t = (terms or '').lower()
    if any(w in t for w in ('anticip', 'prepag', 'prepaid', 'advance', 'contra entrega', 'on delivery', 'cash')):
        return invoice_date
    return invoice_date + timedelta(days=parse_payment_terms_days(terms))


def _status(amount, paid):
    balance = float(amount) - float(paid)
    if balance <= 0.005:
        return 'paid', 0.0
    return ('partial' if paid > 0 else 'open'), round(balance, 2)


def _due_info(due, status, today):
    if status == 'paid' or not due:
        return None, None
    d = (due - today).days
    return (-d if d < 0 else 0), d


# ── Rows ────────────────────────────────────────────────────────────────────
def invoice_rows(invoices, today=None):
    today = today or timezone.localdate()
    invoices = list(invoices)
    pays = {}
    for p in Payment.objects.filter(invoice_ref__in=[i.number for i in invoices]).order_by('payment_date', 'id'):
        pays.setdefault(p.invoice_ref, []).append(p)
    rows = []
    for i in invoices:
        plist = pays.get(i.number, [])
        paid = sum(float(p.amount) for p in plist)
        status, balance = ('cancelled', 0.0) if i.cancelled else _status(i.amount, paid)
        overdue, days_to_due = _due_info(i.due_date, status if not i.cancelled else 'paid', today)
        rows.append({
            'id': i.id, 'deal': i.deal_id, 'number': i.number, 'description': i.description,
            'invoice_date': i.invoice_date.isoformat(), 'due_date': i.due_date.isoformat(),
            'amount': float(i.amount), 'currency': i.currency, 'paid': round(paid, 2), 'balance': balance,
            'status': status, 'days_overdue': overdue or 0, 'days_to_due': days_to_due,
            'cancelled': i.cancelled, 'notes': i.notes,
            'payments': [{'id': p.id, 'amount': float(p.amount), 'currency': p.currency,
                          'payment_date': p.payment_date.isoformat(), 'method': p.method, 'notes': p.notes}
                         for p in plist],
        })
    return rows


def installments(p, paid):
    """
    Split a goods invoice by its order's payment plan. Payments fill the steps
    in order. Each step's due date: invoice date (on order / before shipping),
    shipped date + N days (after shipping), received date (on delivery);
    None while the event hasn't happened.
    """
    from . import plans
    order = p.supplier_order
    steps, source = plans.for_order(order)
    left = paid
    out = []
    for st in steps:
        amt = round(float(p.amount) * st['pct'] / 100, 2)
        if st['when'] in plans.PRE_SHIPPING:
            due = p.invoice_date
        elif st['when'] == 'after_shipping':
            due = order.shipped_date + timedelta(days=st.get('days', 0)) if order.shipped_date else None
        else:
            due = order.received_date
        covered = min(left, amt)
        left -= covered
        out.append({**st, 'amount': amt, 'paid': round(covered, 2),
                    'due_date': due.isoformat() if due else None,
                    'status': 'paid' if covered >= amt - 0.005 else ('partial' if covered > 0 else 'open')})
    return out, plans.describe(steps), source


def payable_rows(payables, today=None):
    today = today or timezone.localdate()
    rows = []
    for p in payables:
        plist = list(p.payments.all())
        paid = sum(float(x.amount) for x in plist)
        status, balance = _status(p.amount, paid)
        inst, plan_text, plan_source, next_note = None, None, None, None
        due = p.due_date
        if p.kind == 'goods' and p.supplier_order_id and status != 'paid':
            inst, plan_text, plan_source = installments(p, paid)
            nxt = next((i for i in inst if i['status'] != 'paid'), None)
            if nxt and nxt['due_date']:
                due = date.fromisoformat(nxt['due_date'])
            elif nxt:
                due = None
                next_note = (f'{nxt["pct"]:g}% due {nxt.get("days", 0)} days after shipping'
                             if nxt['when'] == 'after_shipping' else f'{nxt["pct"]:g}% due on delivery')
        overdue, days_to_due = _due_info(due, status, today)
        cost = p.deal_cost
        rows.append({
            'id': p.id, 'deal': p.deal_id, 'kind': p.kind,
            'payee': p.payee or (p.supplier.company_name if p.supplier else ''),
            'supplier': p.supplier_id,
            'supplier_order': p.supplier_order_id,
            'po_number': p.supplier_order.po_number if p.supplier_order else None,
            'deal_cost': p.deal_cost_id,
            'cost_label': (cost.get_category_display() + (f' ({cost.description})' if cost.description else '')) if cost else None,
            'invoice_ref': p.invoice_ref, 'invoice_date': p.invoice_date.isoformat(),
            'due_date': (due or p.due_date).isoformat(), 'due_known': due is not None,
            'next_due_note': next_note, 'installments': inst, 'plan_text': plan_text, 'plan_source': plan_source,
            'payment_terms': p.payment_terms,
            'amount': float(p.amount), 'currency': p.currency, 'paid': round(paid, 2), 'balance': balance,
            'status': status, 'days_overdue': overdue or 0, 'days_to_due': days_to_due, 'notes': p.notes,
            'payments': [{'id': x.id, 'amount': float(x.amount), 'payment_date': x.payment_date.isoformat(),
                          'method': x.method, 'reference': x.reference, 'notes': x.notes} for x in plist],
        })
    return rows


def _payables_qs():
    return Payable.objects.select_related('supplier', 'supplier_order', 'deal_cost').prefetch_related('payments')


# ── Suggestions for the next client invoice ─────────────────────────────────
def billing_base(deal):
    """
    What the client owes in total, for invoicing and payment rules:
    the processed PO's amount when it has one, else the deal's estimated revenue.
    """
    from apps.clientquotes.models import ClientPO
    po = ClientPO.objects.filter(deal=deal, status='processed', amount__isnull=False).order_by('-processed_at').first()
    if po:
        return float(po.amount), 'po'
    from apps.costs.services import compute
    return compute(deal)['estimate']['revenue'], 'estimate'


STEP_LABEL = {
    'on_order':        ('Advance', 'Anticipo'),
    'before_shipping': ('Before shipping', 'Antes del envío'),
    'after_shipping':  ('Balance', 'Saldo'),
    'on_delivery':     ('On delivery', 'Contra entrega'),
}


def invoice_suggestions(deal, invoiced_total):
    """
    What's left to bill, following the client's payment plan: after the 30%
    advance is invoiced, the next suggestion is the next step, and so on.
    """
    from . import plans
    revenue, revenue_source = billing_base(deal)
    remaining = round(revenue - invoiced_total, 2)
    steps, source = plans.for_deal(deal)
    sugg = []
    if remaining > 0.005:
        start, done = None, 0.0
        for k, st in enumerate(steps):
            if abs(invoiced_total - done) < 0.01:
                start = k
                break
            done += revenue * st['pct'] / 100
        if start is not None and len(steps) > 1:
            for st in steps[start:]:
                en, es = STEP_LABEL[st['when']]
                days = st.get('days', 0) if st['when'] == 'after_shipping' else 0
                tail_en = f', {days} days' if days else ''
                tail_es = f', {days} días' if days else ''
                sugg.append({'description': f'{en} {st["pct"]:g}%{tail_en} ({es} {st["pct"]:g}%{tail_es})',
                             'amount': round(revenue * st['pct'] / 100, 2), 'due_days': days,
                             'due_on_invoice': days == 0})
        else:
            days = steps[0].get('days', 0) if len(steps) == 1 and steps[0]['when'] == 'after_shipping' else 0
            sugg.append({'description': 'Balance (Saldo)' if invoiced_total > 0 else 'Invoice (Factura)',
                         'amount': remaining, 'due_days': days, 'due_on_invoice': days == 0})
    n = ClientInvoice.objects.filter(deal=deal).count() + 1
    base = deal.reference or f'D{deal.pk}'
    while ClientInvoice.objects.filter(number=f'{base}-F{n}').exists():
        n += 1
    return {'revenue': round(revenue, 2), 'revenue_source': revenue_source,
            'invoiced': round(invoiced_total, 2), 'remaining': remaining,
            'suggestions': sugg, 'next_number': f'{base}-F{n}',
            'plan_text': plans.describe(steps), 'plan_source': source}


# ── Per-deal view ────────────────────────────────────────────────────────────
def deal_money(deal):
    today = timezone.localdate()
    inv = invoice_rows(ClientInvoice.objects.filter(deal=deal), today)
    pay = payable_rows(_payables_qs().filter(deal=deal), today)
    live_inv = [r for r in inv if not r['cancelled']]
    invoiced = sum(r['amount'] for r in live_inv)
    received = sum(r['paid'] for r in inv)

    from apps.logistics.models import SupplierOrder
    invoiced_orders = {p['supplier_order'] for p in pay if p['supplier_order']}
    uninvoiced = [{'id': o.id, 'po_number': o.po_number, 'supplier': o.supplier.company_name if o.supplier else None,
                   'total': round(o.total, 2), 'currency': o.currency, 'payment_terms': o.payment_terms,
                   'status': o.status}
                  for o in SupplierOrder.objects.filter(deal=deal).exclude(status='cancelled')
                  .select_related('supplier').prefetch_related('items')
                  if o.id not in invoiced_orders]

    # Supplier-side totals per currency (costs can be in VES etc.).
    by_cur = {}
    for p in pay:
        c = by_cur.setdefault(p['currency'], {'currency': p['currency'], 'owed': 0.0, 'paid': 0.0, 'to_pay': 0.0,
                                                'overdue': 0.0})
        c['owed'] += p['amount']
        c['paid'] += p['paid']
        c['to_pay'] += p['balance']
        if p['days_overdue']:
            c['overdue'] += p['balance']
    return {
        'currency': deal.currency,
        'invoices': inv,
        'payables': pay,
        'uninvoiced_orders': uninvoiced,
        'client': {
            'invoiced': round(invoiced, 2), 'received': round(received, 2),
            'to_collect': round(sum(r['balance'] for r in live_inv), 2),
            'overdue': round(sum(r['balance'] for r in live_inv if r['days_overdue']), 2),
        },
        'suppliers': [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in c.items()} for c in by_cur.values()],
        'next_invoice': invoice_suggestions(deal, invoiced),
        'client_gate': _client_gate(deal),
    }


def _client_gate(deal):
    from .gates import client_money
    return client_money(deal)


# ── Company-wide lists ──────────────────────────────────────────────────────
def _deals_for(user):
    qs = Deal.objects.all()
    if getattr(user, 'role', None) == 'sales':
        qs = qs.filter(owner=user)
    return qs


def _totals(rows):
    out = {}
    for r in rows:
        t = out.setdefault(r['currency'], {'currency': r['currency'], 'outstanding': 0.0, 'overdue': 0.0,
                                           'due_7_days': 0.0, 'count': 0})
        t['outstanding'] += r['balance']
        t['count'] += 1
        if r['days_overdue']:
            t['overdue'] += r['balance']
        elif r['days_to_due'] is not None and r['days_to_due'] <= 7:
            t['due_7_days'] += r['balance']
    return [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()} for t in out.values()]


def _with_deal(rows, deals_by_id):
    for r in rows:
        d = deals_by_id.get(r['deal'])
        r['deal_reference'] = d.reference if d else None
        r['client_name'] = d.client.dropdown_name if d else None
    return rows


def receivables(user, include_paid=False):
    deals = _deals_for(user)
    qs = ClientInvoice.objects.filter(deal__in=deals, cancelled=False).order_by('due_date', 'id')
    rows = invoice_rows(qs)
    if not include_paid:
        rows = [r for r in rows if r['status'] != 'paid']
    deals_by_id = {d.id: d for d in Deal.objects.filter(pk__in={r['deal'] for r in rows}).select_related('client')}
    open_rows = [r for r in rows if r['status'] != 'paid']
    return {'rows': _with_deal(rows, deals_by_id), 'totals': _totals(open_rows)}


def payables(user, include_paid=False):
    deals = _deals_for(user)
    rows = payable_rows(_payables_qs().filter(deal__in=deals).order_by('due_date', 'id'))
    if not include_paid:
        rows = [r for r in rows if r['status'] != 'paid']
    deals_by_id = {d.id: d for d in Deal.objects.filter(pk__in={r['deal'] for r in rows}).select_related('client')}
    open_rows = [r for r in rows if r['status'] != 'paid']
    return {'rows': _with_deal(rows, deals_by_id), 'totals': _totals(open_rows)}


# ── Tracking board ──────────────────────────────────────────────────────────
def _n_days(n):
    return f'{n} day' if n == 1 else f'{n} days'


def board_entries(deals_qs, today):
    out = []
    by_id = {d.id: d for d in deals_qs.select_related('client')}
    for r in invoice_rows(ClientInvoice.objects.filter(deal__in=deals_qs, cancelled=False), today):
        if r['status'] == 'paid' or not r['days_overdue']:
            continue
        d = by_id[r['deal']]
        out.append({
            'kind': 'receivable', 'id': r['id'], 'deal_id': d.id, 'deal_reference': d.reference,
            'client_name': d.client.dropdown_name,
            'title': f'Client invoice {r["number"]}', 'subtitle': r['description'],
            'amount_info': f'{r["currency"]} {r["balance"]:,.2f} still to collect'
                           + (f' of {r["amount"]:,.2f}' if r['paid'] else ''),
            'status': 'overdue', 'status_label': 'Payment overdue',
            'due_date': date.fromisoformat(r['due_date']), 'due_label': 'Due',
            'flags': [{'level': 'late', 'text': f'Client payment {_n_days(r["days_overdue"])} overdue'}],
        })
    for r in payable_rows(_payables_qs().filter(deal__in=deals_qs), today):
        if r['status'] == 'paid':
            continue
        if r['days_overdue']:
            flag = ('late', f'Payment to {r["payee"] or "supplier"} {_n_days(r["days_overdue"])} overdue')
        elif r['days_to_due'] is not None and r['days_to_due'] <= DUE_SOON_DAYS:
            flag = ('warn', 'Due today' if r['days_to_due'] == 0 else f'Due in {_n_days(r["days_to_due"])}')
        else:
            continue
        d = by_id[r['deal']]
        out.append({
            'kind': 'payable', 'id': r['id'], 'deal_id': d.id, 'deal_reference': d.reference,
            'client_name': d.client.dropdown_name,
            'title': f'Pay {r["payee"] or "supplier"}',
            'subtitle': ', '.join(x for x in (r['po_number'] or r['cost_label'],
                                              r['invoice_ref'] and f'invoice {r["invoice_ref"]}') if x),
            'amount_info': f'{r["currency"]} {r["balance"]:,.2f} to pay',
            'status': 'to_pay', 'status_label': 'To pay',
            'due_date': date.fromisoformat(r['due_date']), 'due_label': 'Due',
            'flags': [{'level': flag[0], 'text': flag[1]}],
        })
    # Deals waiting on the client's advance before supplier orders can go out.
    # (Orders waiting on a supplier invoice are flagged on their own board row.)
    from .gates import client_money
    for d in deals_qs.filter(deal_status='active', supplier_orders__status='draft').distinct().select_related('client'):
        c = client_money(d)
        if c['advance_met']:
            continue
        out.append({
            'kind': 'deal', 'id': d.id, 'deal_id': d.id, 'deal_reference': d.reference,
            'client_name': d.client.dropdown_name,
            'title': "Waiting for the client's advance", 'subtitle': f'Terms: {c["plan_text"]}',
            'status': 'awaiting_advance', 'status_label': 'Advance needed',
            'due_date': None, 'due_label': None,
            'flags': [{'level': 'warn', 'text':
                       f'{c["currency"]} {c["advance_required"] - c["received"]:,.2f} to receive before ordering from suppliers'}],
        })

    # Goods received from every supplier, but the client hasn't been invoiced.
    from apps.logistics.models import SupplierOrder
    for d in deals_qs.filter(deal_status='active').select_related('client'):
        orders = [o for o in SupplierOrder.objects.filter(deal=d).exclude(status='cancelled')]
        if not orders or any(o.status != 'received' for o in orders):
            continue
        if ClientInvoice.objects.filter(deal=d, cancelled=False).exists():
            continue
        out.append({
            'kind': 'deal', 'id': d.id, 'deal_id': d.id, 'deal_reference': d.reference,
            'client_name': d.client.dropdown_name,
            'title': 'Invoice the client', 'subtitle': 'All supplier orders received',
            'status': 'to_invoice', 'status_label': 'To invoice',
            'due_date': None, 'due_label': None,
            'flags': [{'level': 'warn', 'text': "Goods received, client not invoiced yet"}],
        })
    return out


# ── Cost invoices → payables ────────────────────────────────────────────────
def sync_cost_payable(cost):
    """Keep a payable in step with a deal cost's invoice (its actual amount)."""
    p = Payable.objects.filter(deal_cost=cost).first()
    if cost.actual_amount is None:
        if p and not p.payments.exists():
            p.delete()
        elif p:
            p.deal_cost = None   # already paid something: keep the record, unlinked
            p.save(update_fields=['deal_cost'])
        return
    inv_date = cost.invoice_date or timezone.localdate()
    if not p:
        p = Payable(deal=cost.deal, kind='cost', deal_cost=cost, due_date=inv_date)
    p.payee = cost.payee or p.payee
    p.invoice_ref = cost.invoice_ref
    p.invoice_date = inv_date
    p.amount = cost.actual_amount
    p.currency = cost.currency
    if p.due_date < p.invoice_date:
        p.due_date = p.invoice_date
    p.save()

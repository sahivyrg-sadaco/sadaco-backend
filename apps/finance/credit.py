"""
Client credit: money a client has paid beyond what they owe.

It arises when a client overpays an invoice, or when a credit note is issued
on an invoice that was already paid (or the invoice is cancelled after payment).
It is held per client and currency, across all their deals, and can be:

  refunded  → a negative 'refund' payment on the invoice(s) holding the surplus
  applied   → moved to another invoice of the same client and currency, on any
              deal: a negative 'credit_out' payment where the surplus sits and a
              positive 'credit_in' payment on the target invoice

Both sides of a move share a transfer_group, so undoing one undoes all of it.
Cash is never counted twice: the surplus leaves the old invoice as it arrives
on the new one.
"""
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.payments.models import Payment
from .models import ClientInvoice
from .services import invoice_rows, log


def sources(client, currency=None):
    """Invoices holding surplus for this client, oldest first: [{invoice, number, deal…, excess}]."""
    invs = (ClientInvoice.objects.filter(deal__client=client, kind='invoice')
            .select_related('deal').order_by('invoice_date', 'id'))
    if currency:
        invs = invs.filter(currency=currency)
    by_id = {i.id: i for i in invs}
    out = []
    for r in invoice_rows(invs):
        if r['excess'] > 0.005:
            inv = by_id[r['id']]
            out.append({'invoice': inv, 'id': inv.id, 'number': inv.number, 'deal_id': inv.deal_id,
                        'deal_reference': inv.deal.reference, 'currency': inv.currency, 'excess': r['excess']})
    return out


def summary(client):
    """{ by_currency: {USD: {available, sources: [...]}}, history: [...] } for one client."""
    by_cur = {}
    for s in sources(client):
        b = by_cur.setdefault(s['currency'], {'available': 0.0, 'sources': []})
        b['available'] = round(b['available'] + s['excess'], 2)
        b['sources'].append({k: v for k, v in s.items() if k != 'invoice'})
    groups = {}
    for p in (Payment.objects.filter(deal__client=client, kind__in=('refund', 'credit_out', 'credit_in'))
              .select_related('deal').order_by('-payment_date', '-id')):
        g = groups.setdefault(p.transfer_group or f'p{p.id}', {
            'group': p.transfer_group, 'date': p.payment_date.isoformat(), 'currency': p.currency,
            'kind': 'refund' if p.kind == 'refund' else 'applied', 'amount': 0.0, 'from': [], 'to': None, 'notes': p.notes})
        if p.kind in ('refund', 'credit_out'):
            g['amount'] = round(g['amount'] + float(-p.amount), 2)
            g['from'].append({'number': p.invoice_ref, 'deal_reference': p.deal.reference if p.deal else ''})
        else:
            g['to'] = {'number': p.invoice_ref, 'deal_reference': p.deal.reference if p.deal else ''}
    return {'by_currency': by_cur, 'history': list(groups.values())}


def _take(srcs, amount):
    """Allocate `amount` over surplus sources, oldest first. → [(source, part)]"""
    left, parts = amount, []
    for s in srcs:
        if left <= 0.005:
            break
        part = round(min(s['excess'], left), 2)
        if part > 0:
            parts.append((s, part))
            left = round(left - part, 2)
    return parts


@transaction.atomic
def refund(client, currency, amount, user, date=None, method='', notes=''):
    srcs = sources(client, currency)
    available = round(sum(s['excess'] for s in srcs), 2)
    if amount <= 0:
        raise ValueError('Enter the amount to refund.')
    if amount > available + 0.005:
        raise ValueError(f'Only {currency} {available:,.2f} of client credit is available.')
    group, when = uuid.uuid4().hex, date or timezone.localdate()
    for s, part in _take(srcs, amount):
        Payment.objects.create(invoice_ref=s['number'], deal=s['invoice'].deal, amount=Decimal(str(-part)), currency=currency,
                               payment_date=when, method=method or 'Refund', notes=notes, recorded_by=user,
                               kind='refund', transfer_group=group)
        log(s['invoice'].deal, user, f'Client credit refunded: {currency} {part:,.2f} from {s["number"]}'
                                     + (f' ({notes})' if notes else '') + '.')
    return group


@transaction.atomic
def apply(client, target, amount, user, date=None):
    if target.kind != 'invoice' or target.cancelled:
        raise ValueError('Client credit can only be applied to a live invoice.')
    if target.deal.client_id != client.id:
        raise ValueError('That invoice belongs to a different client.')
    owed = invoice_rows([target])[0]['balance']
    srcs = [s for s in sources(client, target.currency) if s['id'] != target.id]
    available = round(sum(s['excess'] for s in srcs), 2)
    if amount <= 0:
        raise ValueError('Enter the amount to apply.')
    if amount > available + 0.005:
        raise ValueError(f'Only {target.currency} {available:,.2f} of client credit is available.')
    if amount > owed + 0.005:
        raise ValueError(f'{target.number} only has {target.currency} {owed:,.2f} left to pay.')
    group, when = uuid.uuid4().hex, date or timezone.localdate()
    parts = _take(srcs, amount)
    from_numbers = ', '.join(s['number'] for s, _ in parts)
    for s, part in parts:
        Payment.objects.create(invoice_ref=s['number'], deal=s['invoice'].deal, amount=Decimal(str(-part)),
                               currency=target.currency, payment_date=when, method=f'Credit moved to {target.number}',
                               recorded_by=user, kind='credit_out', transfer_group=group)
        log(s['invoice'].deal, user, f'Client credit of {target.currency} {part:,.2f} on {s["number"]} '
                                     f'applied to {target.number} ({target.deal.reference}).')
    Payment.objects.create(invoice_ref=target.number, deal=target.deal, amount=Decimal(str(amount)), currency=target.currency,
                           payment_date=when, method='Client credit', notes=f'From {from_numbers}', recorded_by=user,
                           kind='credit_in', transfer_group=group)
    log(target.deal, user, f'Client credit applied to {target.number}: {target.currency} {amount:,.2f} (from {from_numbers}).')
    return group


@transaction.atomic
def undo(group, user):
    rows = list(Payment.objects.filter(transfer_group=group).select_related('deal'))
    if not rows:
        raise ValueError('Nothing to undo.')
    for d in {p.deal for p in rows if p.deal}:
        log(d, user, 'Client credit move undone.' if any(p.kind != 'refund' for p in rows) else 'Client credit refund undone.')
    Payment.objects.filter(transfer_group=group).delete()

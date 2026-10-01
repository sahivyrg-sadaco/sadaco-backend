"""Client quote snapshots, PO processing, and reminders."""
from datetime import timedelta

from django.utils import timezone

from apps.deals.models import Deal, DealActivity
from .models import ClientPO, ClientQuote

NO_REPLY_DAYS = 7
DEFAULT_VALID_DAYS = 15
STAGE_ORDER = ['Quoting', 'Negotiating', "Client's PO Received", 'PO Sent', 'Invoiced', 'Delivered', 'Closed']
SPANISH_COUNTRIES = {'venezuela', 'colombia', 'mexico', 'méxico', 'spain', 'españa', 'argentina', 'chile', 'peru',
                     'perú', 'ecuador', 'panama', 'panamá', 'uruguay', 'paraguay', 'bolivia', 'costa rica'}


def log(deal, user, text):
    DealActivity.objects.create(deal=deal, user=user if getattr(user, 'is_authenticated', False) else None,
                                activity_type='client_quote', description=text)


def advance_stage(deal, stage, user):
    """Move the deal forward to `stage` if it's earlier in the pipeline (never backwards)."""
    try:
        if STAGE_ORDER.index(deal.status) >= STAGE_ORDER.index(stage):
            return
    except ValueError:
        return
    deal.status = stage
    deal.save(update_fields=['status'])
    log(deal, user, f'Stage moved to {stage}.')


def default_language(deal):
    country = (deal.client.country or '').strip().lower() if deal.client else ''
    return 'es' if not country or country in SPANISH_COUNTRIES else 'en'


def current_snapshot(deal):
    """What a quote made now would contain, plus anything that stops it being made."""
    from apps.costs.services import compute
    from apps.finance import plans
    items = list(deal.items.filter(is_split_child=False).order_by('item_number', 'id'))
    lines, problems = [], []
    for k, it in enumerate(items, 1):
        price = float(it.unit_price or 0)
        qty = float(it.qty or 0)
        if price <= 0:
            problems.append(f'Line {k} ({it.description[:40]}) has no sell price.')
        if qty <= 0:
            problems.append(f'Line {k} ({it.description[:40]}) has no quantity.')
        lines.append({'n': k, 'description': it.description, 'part_number': it.part_number, 'brand': it.brand,
                      'model': getattr(it, 'model_name', '') or '', 'qty': qty, 'unit': it.unit,
                      'unit_price': round(price, 4), 'total': round(qty * price, 2)})
    if not items:
        problems.append('The deal has no line items.')
    econ = compute(deal)
    from apps.costs.models import DealCost
    labels = {c.id: (c.category, c.get_category_display(), c.description) for c in DealCost.objects.filter(deal=deal)}
    charges = []
    for r in econ['rows']:
        if r['treatment'] == 'separate' and (r['charge'] or 0) > 0:
            key, cat, desc = labels.get(r['id'], ('other', 'Charge', ''))
            charges.append({'category': key, 'label': cat, 'detail': desc, 'amount': round(r['charge'], 2)})
    steps, _ = plans.for_deal(deal)
    total = round(sum(l['total'] for l in lines) + sum(c['amount'] for c in charges), 2)
    return {
        'lines': lines, 'charges': charges, 'total': total, 'currency': deal.currency,
        'payment_terms': deal.payment_terms or plans.describe(steps),
        'incoterm': deal.incoterm or '', 'delivery_point': deal.port_location or '',
        'delivery_time': deal.delivery_time or '',
        'problems': problems,
    }


def _signature(snap):
    """What matters for 'has the deal changed since this quote?'"""
    return (
        tuple((l['description'], l['qty'], round(float(l['unit_price']), 2)) for l in snap['lines']),
        tuple((c['label'], round(float(c['amount']), 2)) for c in snap['charges']),
        snap['payment_terms'], snap['incoterm'], snap['delivery_point'],
    )


def changed_since(quote, snap):
    q = {'lines': quote.lines, 'charges': quote.charges, 'payment_terms': quote.payment_terms,
         'incoterm': quote.incoterm, 'delivery_point': quote.delivery_point}
    return _signature(q) != _signature(snap)


def po_status(deal):
    """{ processed: bool, message } — supplier orders need a processed client PO."""
    pos = list(ClientPO.objects.filter(deal=deal))
    if any(p.status == 'processed' for p in pos):
        return {'processed': True, 'message': None}
    pending = [p for p in pos if p.status == 'received']
    if pending:
        msg = f"Process the client's purchase order {pending[0].po_number} first (Client quote tab)."
    else:
        msg = "The client's purchase order hasn't been received and processed yet (Client quote tab)."
    return {'processed': False, 'message': msg}


def board_entries(deals_qs, today):
    out = []
    by_id = {d.id: d for d in deals_qs.select_related('client')}
    for q in ClientQuote.objects.filter(deal__in=deals_qs, status='sent'):
        d = by_id[q.deal_id]
        if ClientPO.objects.filter(deal=d).exclude(status='rejected').exists():
            continue
        flags = []
        if q.valid_until < today:
            flags.append(('warn', f'Quote expired {(today - q.valid_until).days} days ago with no PO'))
        else:
            waited = (today - (q.last_followup_date or q.sent_date or q.issue_date)).days
            if waited >= NO_REPLY_DAYS:
                flags.append(('warn', f'No reply from the client in {waited} days'))
        if not flags:
            continue
        out.append({
            'kind': 'client_quote', 'id': q.id, 'deal_id': d.id, 'deal_reference': d.reference,
            'client_name': d.client.dropdown_name,
            'title': f'Quote {q.number}', 'subtitle': f'{q.currency} {float(q.total):,.2f}, sent {q.sent_date:%b %d}',
            'status': 'quote_sent', 'status_label': 'Awaiting PO',
            'due_date': q.valid_until, 'due_label': 'Valid until',
            'flags': [{'level': l, 'text': t} for l, t in flags],
        })
    for p in ClientPO.objects.filter(deal__in=deals_qs, status='received'):
        d = by_id[p.deal_id]
        out.append({
            'kind': 'client_po', 'id': p.id, 'deal_id': d.id, 'deal_reference': d.reference,
            'client_name': d.client.dropdown_name,
            'title': f'Client PO {p.po_number}', 'subtitle': f'Received {p.received_date:%b %d}',
            'status': 'po_to_process', 'status_label': 'To process',
            'due_date': None, 'due_label': None,
            'flags': [{'level': 'warn', 'text': 'Check it against the quote and process it before ordering from suppliers'}],
        })
    return out

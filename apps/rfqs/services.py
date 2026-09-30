"""RFQ rules: linking replies to quotes, and reminders for the tracking board."""
from django.utils import timezone

from apps.deals.models import Deal, DealActivity
from .models import SupplierRFQ

NO_REPLY_DAYS   = 5   # without a reply-by date, flag after this long
CHASE_GAP_DAYS  = 3   # after a reminder, give them this long before flagging again
QUOTING_IDLE_DAYS = 1  # a Quoting deal with items and no RFQs, after this long


def _n_days(n):
    return f'{n} day' if n == 1 else f'{n} days'


def log(deal, user, text):
    DealActivity.objects.create(deal=deal, user=user if getattr(user, 'is_authenticated', False) else None,
                                activity_type='rfq', description=text)


def sync_replies(rfqs):
    """
    Mark awaiting RFQs as replied when that supplier's quote exists on the deal,
    however it was entered. Each quote answers at most one RFQ.
    """
    from apps.quotes.models import SupplierQuote
    awaiting = [r for r in rfqs if r.status == 'awaiting' and r.supplier_id]
    if not awaiting:
        return
    used = set(SupplierRFQ.objects.filter(supplier_quote__isnull=False).values_list('supplier_quote_id', flat=True))
    for r in sorted(awaiting, key=lambda x: (x.sent_date, x.id)):
        q = (SupplierQuote.objects.filter(deal_id=r.deal_id, supplier_id=r.supplier_id)
             .exclude(pk__in=used).order_by('created_at').first())
        if q:
            r.status = 'replied'
            r.supplier_quote = q
            r.replied_date = max(timezone.localtime(q.created_at).date(), r.sent_date)
            r.save(update_fields=['status', 'supplier_quote', 'replied_date', 'updated_at'])
            used.add(q.id)


def rfq_flags(r, today):
    """Reminders for one awaiting RFQ."""
    if r.status != 'awaiting':
        return []
    if r.last_followup_date and (today - r.last_followup_date).days < CHASE_GAP_DAYS:
        return []   # reminder just sent: give them a moment
    reminders = ('no reminder sent' if not r.followup_count
                 else f'{r.followup_count} reminder{"s" if r.followup_count > 1 else ""} sent')
    if r.reply_by and r.reply_by < today:
        return [('late', f'No reply, {_n_days((today - r.reply_by).days)} past the reply-by date ({reminders})')]
    waited = (today - r.sent_date).days
    if not r.reply_by and waited >= NO_REPLY_DAYS:
        return [('warn', f'No reply after {_n_days(waited)} ({reminders})')]
    return []


def board_entries(deals_qs, today):
    """Awaiting RFQs, plus Quoting deals where nothing has been sent to suppliers."""
    rfqs = list(SupplierRFQ.objects.filter(deal__in=deals_qs, status='awaiting')
                .select_related('deal', 'deal__client', 'supplier').prefetch_related('deal_items'))
    sync_replies(rfqs)
    out = []
    for r in rfqs:
        if r.status != 'awaiting':
            continue
        items = list(r.deal_items.all())
        names = ', '.join(i.description.splitlines()[0][:40] for i in items[:2])
        if len(items) > 2:
            names += f', +{len(items) - 2} more'
        waited = (today - r.sent_date).days
        out.append({
            'kind': 'rfq', 'id': r.id,
            'deal_id': r.deal_id, 'deal_reference': r.deal.reference, 'client_name': r.deal.client.dropdown_name,
            'title': f'RFQ to {r.supplier.company_name if r.supplier else "a removed supplier"}',
            'subtitle': f'{len(items)} item{"" if len(items) == 1 else "s"}: {names}' if items else '',
            'sent_to': r.sent_to,
            'sent_info': ('Sent today' if waited == 0 else f'Sent {r.sent_date:%b %d}, waiting {_n_days(waited)}')
                         + (f', {r.followup_count} reminder{"s" if r.followup_count > 1 else ""}'
                            if r.followup_count else ''),
            'status': 'awaiting', 'status_label': 'Awaiting reply',
            'due_date': r.reply_by, 'due_label': 'Reply by' if r.reply_by else None,
            'flags': [{'level': l, 'text': t} for l, t in rfq_flags(r, today)],
        })

    from apps.quotes.models import SupplierQuote
    idle_before = timezone.now() - timezone.timedelta(days=QUOTING_IDLE_DAYS)
    quoting = (deals_qs.filter(status='Quoting', deal_status='active', created_at__lte=idle_before)
               .exclude(rfqs__isnull=False).select_related('client'))
    with_quotes = set(SupplierQuote.objects.filter(deal__in=quoting).values_list('deal_id', flat=True))
    for d in quoting:
        if d.id in with_quotes or not d.items.filter(is_split_child=False).exists():
            continue
        age = (today - timezone.localtime(d.created_at).date()).days
        out.append({
            'kind': 'deal', 'id': d.id,
            'deal_id': d.id, 'deal_reference': d.reference, 'client_name': d.client.dropdown_name,
            'title': 'Send RFQs to suppliers', 'subtitle': f'Opened {_n_days(age)} ago',
            'status': 'to_quote', 'status_label': 'To quote',
            'due_date': None, 'due_label': None,
            'flags': [{'level': 'warn', 'text': 'No supplier has been asked for a quote yet'}],
        })
    return out

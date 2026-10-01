"""Client quotes (versions, sending, follow-up) and client purchase orders."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deals.models import Deal
from . import services
from .models import ClientPO, ClientQuote

QUOTE_ROLES = ('admin', 'sales', 'finance')


def _forbid(request):
    if getattr(request.user, 'role', None) not in QUOTE_ROLES:
        return Response({'error': 'Only admin, sales and finance users can do this.'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _bad(msg, field=None):
    return Response({field: [msg]} if field else {'error': msg}, status=status.HTTP_400_BAD_REQUEST)


def _date(v, default=None):
    if v in (None, ''):
        return default
    return date.fromisoformat(str(v)[:10])


def _quote_json(q, snap):
    return {
        'id': q.id, 'deal': q.deal_id, 'version': q.version, 'number': q.number, 'status': q.status,
        'status_label': q.get_status_display(), 'language': q.language,
        'issue_date': q.issue_date.isoformat(), 'valid_until': q.valid_until.isoformat(),
        'expired': q.status == 'sent' and q.valid_until < timezone.localdate(),
        'currency': q.currency, 'lines': q.lines, 'charges': q.charges, 'total': float(q.total),
        'payment_terms': q.payment_terms, 'incoterm': q.incoterm, 'delivery_point': q.delivery_point,
        'delivery_time': q.delivery_time, 'client_ref': q.client_ref, 'notes': q.notes,
        'sent_date': q.sent_date.isoformat() if q.sent_date else None, 'sent_to': q.sent_to,
        'subject': q.subject, 'body': q.body, 'followup_count': q.followup_count,
        'last_followup_date': q.last_followup_date.isoformat() if q.last_followup_date else None,
        'decline_reason': q.decline_reason,
        'changed_since': q.status in ('draft', 'sent') and services.changed_since(q, snap),
    }


def _po_json(p):
    return {
        'id': p.id, 'deal': p.deal_id, 'quote': p.quote_id, 'quote_number': p.quote.number if p.quote else None,
        'quote_total': float(p.quote.total) if p.quote else None,
        'po_number': p.po_number, 'po_date': p.po_date.isoformat(), 'received_date': p.received_date.isoformat(),
        'amount': float(p.amount) if p.amount is not None else None, 'currency': p.currency,
        'attachment_id': p.attachment_id, 'status': p.status, 'status_label': p.get_status_display(),
        'checks': p.checks, 'notes': p.notes, 'reject_reason': p.reject_reason,
        'processed_by': p.processed_by.name if p.processed_by else None,
        'processed_at': p.processed_at.isoformat() if p.processed_at else None,
    }


def _payload(deal):
    snap = services.current_snapshot(deal)
    client = deal.client
    return {
        'quotes': [_quote_json(q, snap) for q in ClientQuote.objects.filter(deal=deal)],
        'pos': [_po_json(p) for p in ClientPO.objects.filter(deal=deal).select_related('quote', 'processed_by')],
        'current': snap,
        'po_status': services.po_status(deal),
        'defaults': {
            'language': services.default_language(deal), 'valid_days': services.DEFAULT_VALID_DAYS,
            'client_email': client.contact_email if client else '', 'client_contact': client.contact_name if client else '',
        },
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def deal_quotes(request, pk):
    """GET /api/deals/{id}/client-quotes/  ·  POST creates the next version as a draft."""
    deal = get_object_or_404(Deal.objects.select_related('client'), pk=pk)
    if request.method == 'GET':
        return Response(_payload(deal))
    if (r := _forbid(request)):
        return r
    snap = services.current_snapshot(deal)
    if snap['problems']:
        return _bad(' '.join(snap['problems']))
    d = request.data
    today = timezone.localdate()
    try:
        valid_until = _date(d.get('valid_until')) or today + timedelta(days=int(d.get('valid_days') or services.DEFAULT_VALID_DAYS))
    except (TypeError, ValueError):
        return _bad('Enter a valid date.', 'valid_until')
    if valid_until < today:
        return _bad('The quote would already be expired.', 'valid_until')
    with transaction.atomic():
        # Only one draft at a time: replace an unsent draft rather than piling them up.
        ClientQuote.objects.filter(deal=deal, status='draft').delete()
        version = (ClientQuote.objects.filter(deal=deal).order_by('-version').values_list('version', flat=True).first() or 0) + 1
        base = deal.reference or f'D{deal.pk}'
        number = f'{base}-Q{version}'
        while ClientQuote.objects.filter(number=number).exists():
            version += 1
            number = f'{base}-Q{version}'
        q = ClientQuote.objects.create(
            deal=deal, version=version, number=number,
            language=d.get('language') if d.get('language') in ('es', 'en') else services.default_language(deal),
            issue_date=today, valid_until=valid_until, currency=snap['currency'],
            lines=snap['lines'], charges=snap['charges'], total=Decimal(str(snap['total'])),
            payment_terms=snap['payment_terms'], incoterm=snap['incoterm'],
            delivery_point=snap['delivery_point'], delivery_time=snap['delivery_time'],
            client_ref=(deal.client_ref if (deal.client_ref or '').lower() != 'xxx-xxx' else ''),
            notes=str(d.get('notes') or ''), created_by=request.user)
    services.log(deal, request.user, f'Client quote {q.number} prepared: {q.currency} {q.total:,.2f}.')
    return Response(_payload(deal), status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def quote_detail(request, qid):
    """PUT /api/client-quotes/{id}/ { notes, valid_until, language, status: 'declined', decline_reason }
       DELETE only for drafts."""
    q = get_object_or_404(ClientQuote.objects.select_related('deal', 'deal__client'), pk=qid)
    deal = q.deal
    if (r := _forbid(request)):
        return r
    if request.method == 'DELETE':
        if q.status != 'draft':
            return _bad('Only a draft can be deleted. A sent quote stays on record.')
        q.delete()
        return Response(_payload(deal))
    d = request.data
    if q.status == 'draft':
        if 'notes' in d:
            q.notes = str(d['notes'] or '')
        if 'language' in d and d['language'] in ('es', 'en'):
            q.language = d['language']
    if 'valid_until' in d:
        try:
            q.valid_until = _date(d['valid_until'], q.valid_until)
        except ValueError:
            return _bad('Enter a valid date.', 'valid_until')
    if d.get('status') == 'declined' and q.status == 'sent':
        q.status = 'declined'
        q.decline_reason = str(d.get('decline_reason') or '').strip()
        services.log(deal, request.user, f'Client declined quote {q.number}'
                     + (f': {q.decline_reason}' if q.decline_reason else '.'))
    elif d.get('status') == 'sent' and q.status == 'declined':
        q.status = 'sent'
        services.log(deal, request.user, f'Quote {q.number} reopened.')
    q.save()
    return Response(_payload(deal))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def quote_sent(request, qid):
    """POST /api/client-quotes/{id}/sent/ { sent_to, subject, body } → logs it as sent today."""
    q = get_object_or_404(ClientQuote.objects.select_related('deal'), pk=qid)
    if (r := _forbid(request)):
        return r
    if q.status != 'draft':
        return _bad('This quote has already been sent.')
    d = request.data
    with transaction.atomic():
        ClientQuote.objects.filter(deal=q.deal, status='sent').update(status='superseded')
        q.status = 'sent'
        q.sent_date = timezone.localdate()
        q.sent_to = str(d.get('sent_to') or '').strip()
        q.subject = str(d.get('subject') or '').strip()
        q.body = str(d.get('body') or '')
        q.save()
    services.log(q.deal, request.user, f'Quote {q.number} sent to the client'
                 + (f' ({q.sent_to})' if q.sent_to else '') + f': {q.currency} {q.total:,.2f}.')
    services.advance_stage(q.deal, 'Negotiating', request.user)
    return Response(_payload(q.deal))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def quote_followup(request, qid):
    """POST /api/client-quotes/{id}/followup/ → logs a reminder sent today."""
    q = get_object_or_404(ClientQuote.objects.select_related('deal'), pk=qid)
    if (r := _forbid(request)):
        return r
    q.followup_count += 1
    q.last_followup_date = timezone.localdate()
    q.save(update_fields=['followup_count', 'last_followup_date', 'updated_at'])
    services.log(q.deal, request.user, f'Reminder {q.followup_count} sent to the client about quote {q.number}.')
    return Response(_payload(q.deal))


# ── Client purchase orders ──────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_po(request, pk):
    """POST /api/deals/{id}/client-pos/ { quote, po_number, po_date, amount, attachment_id, notes }"""
    deal = get_object_or_404(Deal, pk=pk)
    if (r := _forbid(request)):
        return r
    d = request.data
    number = str(d.get('po_number') or '').strip()
    if not number:
        return _bad("Enter the client's PO number.", 'po_number')
    quote = ClientQuote.objects.filter(pk=d.get('quote'), deal=deal).first() if d.get('quote') else None
    try:
        po_date = _date(d.get('po_date'), timezone.localdate())
        amount = Decimal(str(d['amount'])).quantize(Decimal('0.01')) if d.get('amount') not in (None, '') else None
    except (ValueError, InvalidOperation):
        return _bad('Check the date and amount.')
    with transaction.atomic():
        p = ClientPO.objects.create(
            deal=deal, quote=quote, po_number=number, po_date=po_date, received_date=timezone.localdate(),
            amount=amount, currency=deal.currency, attachment_id=d.get('attachment_id') or None,
            notes=str(d.get('notes') or ''), created_by=request.user)
        if quote and quote.status in ('sent', 'superseded', 'declined'):
            quote.status = 'accepted'
            quote.save(update_fields=['status', 'updated_at'])
    services.log(deal, request.user, f"Client PO {p.po_number} received"
                 + (f' for quote {quote.number}' if quote else '') + '. It needs processing before supplier orders.')
    return Response(_payload(deal), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_po(request, pid):
    """
    POST /api/client-pos/{id}/process/ { checks: { items, amount, terms }, notes }
    All three confirmations are required. Processing moves the deal to
    "Client's PO Received", marks it won, and stores the PO number as the
    client's reference if none was set.
    """
    p = get_object_or_404(ClientPO.objects.select_related('deal', 'quote'), pk=pid)
    deal = p.deal
    if (r := _forbid(request)):
        return r
    if p.status != 'received':
        return _bad('This PO has already been handled.')
    checks = request.data.get('checks') or {}
    missing = [k for k in ('items', 'amount', 'terms') if not checks.get(k)]
    if missing:
        return _bad('Confirm every check before processing: items and quantities, amount, and terms.')
    with transaction.atomic():
        p.status = 'processed'
        p.checks = {k: True for k in ('items', 'amount', 'terms')}
        if request.data.get('notes'):
            p.notes = (p.notes + '\n' if p.notes else '') + str(request.data['notes'])
        p.processed_by = request.user
        p.processed_at = timezone.now()
        p.save()
        if not deal.client_ref or deal.client_ref.lower() == 'xxx-xxx':
            deal.client_ref = p.po_number
        deal.deal_status = 'won'
        deal.save(update_fields=['client_ref', 'deal_status'])
    diff = ''
    if p.quote and p.amount is not None and abs(float(p.amount) - float(p.quote.total)) > 0.005:
        diff = f' Amount differs from the quote by {p.currency} {float(p.amount) - float(p.quote.total):,.2f} (accepted).'
    services.log(deal, request.user, f'Client PO {p.po_number} processed. Supplier orders can now be placed.{diff}')
    services.advance_stage(deal, "Client's PO Received", request.user)
    return Response(_payload(deal))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_po(request, pid):
    """POST /api/client-pos/{id}/reject/ { reason }"""
    p = get_object_or_404(ClientPO.objects.select_related('deal'), pk=pid)
    if (r := _forbid(request)):
        return r
    reason = str(request.data.get('reason') or '').strip()
    if not reason:
        return _bad('Say why the PO is rejected, e.g. "Prices differ from our quote".', 'reason')
    if p.status != 'received':
        return _bad('This PO has already been handled.')
    p.status = 'rejected'
    p.reject_reason = reason
    p.save(update_fields=['status', 'reject_reason'])
    services.log(p.deal, request.user, f'Client PO {p.po_number} rejected: {reason}')
    return Response(_payload(p.deal))

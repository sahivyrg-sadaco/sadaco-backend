"""RFQs for a deal: log, follow up, close."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deals.models import Deal
from . import services
from .models import SupplierRFQ
from .serializers import SupplierRFQSerializer


RFQ_ROLES = ('admin', 'sales', 'operations')


def _denied():
    return Response({'error': 'Only admin, sales and operations users can send or change RFQs.'},
                    status=status.HTTP_403_FORBIDDEN)


def _qs():
    return SupplierRFQ.objects.select_related('supplier').prefetch_related('deal_items')


def _list(deal):
    rfqs = list(_qs().filter(deal=deal))
    services.sync_replies(rfqs)
    return SupplierRFQSerializer(rfqs, many=True).data


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def deal_rfqs(request, pk):
    """GET /api/deals/{id}/rfqs/ → list.  POST logs one RFQ as sent → the new list."""
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == 'POST':
        if getattr(request.user, 'role', None) not in RFQ_ROLES:
            return _denied()
        data = request.data.copy()
        data.setdefault('sent_date', timezone.localdate().isoformat())
        ser = SupplierRFQSerializer(data=data, context={'deal': deal})
        ser.is_valid(raise_exception=True)
        r = ser.save(deal=deal, created_by=request.user)
        n = r.deal_items.count()
        services.log(deal, request.user,
                     f'RFQ sent to {r.supplier.company_name if r.supplier else "supplier"} '
                     f'({n} item{"" if n == 1 else "s"}).')
        return Response(_list(deal), status=status.HTTP_201_CREATED)
    return Response(_list(deal))


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def rfq_detail(request, rid):
    """PUT/DELETE /api/rfqs/{id}/ → the deal's RFQ list."""
    r = get_object_or_404(_qs().select_related('deal'), pk=rid)
    deal = r.deal
    if getattr(request.user, 'role', None) not in RFQ_ROLES:
        return _denied()
    if request.method == 'DELETE':
        r.delete()
        return Response(_list(deal))
    old = r.status
    ser = SupplierRFQSerializer(r, data=request.data, partial=True, context={'deal': deal})
    ser.is_valid(raise_exception=True)
    r = ser.save()
    if r.status != old:
        who = r.supplier.company_name if r.supplier else 'Supplier'
        text = {'declined': f'{who} declined to quote.', 'closed': f'RFQ to {who} closed without a reply.',
                'awaiting': f'RFQ to {who} reopened.'}.get(r.status)
        if text:
            services.log(deal, request.user, text)
    return Response(_list(deal))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rfq_followup(request, rid):
    """POST /api/rfqs/{id}/followup/ { reply_by? } → logs a reminder sent today."""
    r = get_object_or_404(SupplierRFQ.objects.select_related('deal', 'supplier'), pk=rid)
    if getattr(request.user, 'role', None) not in RFQ_ROLES:
        return _denied()
    r.followup_count += 1
    r.last_followup_date = timezone.localdate()
    if request.data.get('reply_by'):
        r.reply_by = request.data['reply_by']
    r.save()
    services.log(r.deal, request.user,
                 f'Reminder {r.followup_count} sent to {r.supplier.company_name if r.supplier else "supplier"}.')
    return Response(_list(r.deal))

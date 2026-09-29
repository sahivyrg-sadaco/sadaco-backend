"""Extra costs and economics for a deal."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deals.models import Deal, DealActivity
from . import services
from .models import TREATMENTS, DealCost, DealCostSettings
from .serializers import DealCostSerializer


def _log(deal, user, text):
    DealActivity.objects.create(deal=deal, user=user, activity_type='costs', description=text)


def _payload(deal):
    costs = list(DealCost.objects.filter(deal=deal).select_related('shipment'))
    return {
        'costs': DealCostSerializer(costs, many=True).data,
        'economics': services.compute(deal, costs=costs),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def deal_costs(request, pk):
    """GET /api/deals/{id}/costs/ → { costs, economics }.  POST adds one cost."""
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == 'POST':
        ser = DealCostSerializer(data=request.data, context={'deal': deal})
        ser.is_valid(raise_exception=True)
        c = ser.save(deal=deal, created_by=request.user)
        _log(deal, request.user, f'Cost added: {c.get_category_display()}'
             + (f' ({c.description})' if c.description else '') + '.')
        return Response(_payload(deal), status=status.HTTP_201_CREATED)
    return Response(_payload(deal))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_typical(request, pk):
    """POST /api/deals/{id}/costs/typical/ → adds the costs the incoterm usually involves."""
    deal = get_object_or_404(Deal, pk=pk)
    if not deal.incoterm:
        return Response({'error': "Set the deal's incoterm first, so we know which costs to expect."},
                        status=status.HTTP_400_BAD_REQUEST)
    created = services.add_typical(deal, request.user)
    if created:
        _log(deal, request.user, f'Typical costs for {deal.incoterm} added: '
             + ', '.join(c.get_category_display().lower() for c in created) + '.')
    data = _payload(deal)
    data['created'] = len(created)
    return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def cost_settings(request, pk):
    """PUT /api/deals/{id}/cost-settings/ { default_treatment } — '' goes back to the incoterm default."""
    deal = get_object_or_404(Deal, pk=pk)
    t = request.data.get('default_treatment') or ''
    if t and t not in dict(TREATMENTS):
        return Response({'error': 'Unknown option.'}, status=status.HTTP_400_BAD_REQUEST)
    if t:
        DealCostSettings.objects.update_or_create(deal=deal, defaults={'default_treatment': t})
    else:
        DealCostSettings.objects.filter(deal=deal).delete()
    return Response(_payload(deal))


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def cost_detail(request, cid):
    """PUT/DELETE /api/costs/{id}/ → returns the deal's { costs, economics }."""
    c = get_object_or_404(DealCost.objects.select_related('deal'), pk=cid)
    deal = c.deal
    if request.method == 'DELETE':
        if c.shipment_id:
            return Response({'error': 'This cost comes from a shipment. Remove the freight cost on the shipment instead.'},
                            status=status.HTTP_400_BAD_REQUEST)
        _log(deal, request.user, f'Cost removed: {c.get_category_display()}'
             + (f' ({c.description})' if c.description else '') + '.')
        c.delete()
        return Response(_payload(deal))

    had_actual = c.actual_amount is not None
    old_actual = c.actual_amount
    ser = DealCostSerializer(c, data=request.data, partial=True, context={'deal': deal})
    ser.is_valid(raise_exception=True)
    c = ser.save()
    if c.actual_amount != old_actual:
        c.overrun_acknowledged = False   # a new invoice amount deserves a fresh look
        c.save(update_fields=['overrun_acknowledged'])
        if not had_actual and c.actual_amount is not None:
            _log(deal, request.user, f'Invoice recorded for {c.get_category_display().lower()}: '
                 f'{c.currency} {c.actual_amount:,.2f}.')
    return Response(_payload(deal))

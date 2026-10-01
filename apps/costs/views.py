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
    from .freight import freight_by_item
    costs = list(DealCost.objects.filter(deal=deal).select_related('shipment'))
    return {
        'costs': DealCostSerializer(costs, many=True).data,
        'economics': services.compute(deal, costs=costs),
        'freight_by_item': freight_by_item(deal),
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
             + ', '.join(c.get_category_display() for c in created) + '.')
    data = _payload(deal)
    data['created'] = len(created)
    return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def cost_settings(request, pk):
    """
    PUT /api/deals/{id}/cost-settings/ { default_treatment?, target_margin_pct? }
    Send '' / null for either to go back to the company standard.
    """
    from decimal import Decimal, InvalidOperation
    deal = get_object_or_404(Deal, pk=pk)
    s, _ = DealCostSettings.objects.get_or_create(deal=deal)
    d = request.data
    if 'default_treatment' in d:
        t = d.get('default_treatment') or ''
        if t and t not in dict(TREATMENTS):
            return Response({'error': 'Unknown option.'}, status=status.HTTP_400_BAD_REQUEST)
        s.default_treatment = t
    if 'target_margin_pct' in d:
        v = d.get('target_margin_pct')
        if v in (None, ''):
            s.target_margin = None
        else:
            try:
                pct = Decimal(str(v))
            except (InvalidOperation, ValueError):
                return Response({'target_margin_pct': ['Enter a percentage.']}, status=status.HTTP_400_BAD_REQUEST)
            if not (0 <= pct < 100):
                return Response({'target_margin_pct': ['Use a margin from 0 to 99%.']}, status=status.HTTP_400_BAD_REQUEST)
            s.target_margin = (pct / 100).quantize(Decimal('0.0001'))
            _log(deal, request.user, f'Target margin for this deal set to {pct:g}%.')
    if not s.default_treatment and s.target_margin is None and not s.transit_days:
        s.delete()
    else:
        s.save()
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
    old_estimate = c.estimate_amount
    ser = DealCostSerializer(c, data=request.data, partial=True, context={'deal': deal})
    ser.is_valid(raise_exception=True)
    c = ser.save()
    if c.basis == 'weight' and c.estimate_amount != old_estimate and old_estimate:
        # Estimate edited by hand: scale the per-line split to match.
        k = float(c.estimate_amount or 0) / float(old_estimate)
        c.breakdown = [{**b, 'amount': round(float(b.get('amount') or 0) * k, 2)} for b in c.breakdown or []]
        c.save(update_fields=['breakdown'])
    if c.actual_amount != old_actual:
        c.overrun_acknowledged = False   # a new invoice amount deserves a fresh look
        c.save(update_fields=['overrun_acknowledged'])
        if not had_actual and c.actual_amount is not None:
            _log(deal, request.user, f'Invoice recorded for {c.get_category_display()}: '
                 f'{c.currency} {c.actual_amount:,.2f}.')
    return Response(_payload(deal))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def freight_estimate(request, pk):
    """
    GET  /api/deals/{id}/freight-estimate/ → per-line weights and lead times, saved rates
    POST { lines: [{deal_item, unit_kg}], legs: [{category, rate_per_kg, min_charge}] }
         → writes the freight cost rows; returns { estimate, costs, economics, freight_by_item }
    """
    from . import freight
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == 'POST':
        try:
            written = freight.save_estimate(deal, request.data.get('lines') or [], request.data.get('legs') or [],
                                            request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if written:
            _log(deal, request.user, 'Freight estimated by weight: '
                 + '; '.join(f'{c.get_category_display()} {c.currency} {c.estimate_amount:,.2f}' for c in written) + '.')
        return Response({'estimate': freight.item_logistics(deal), **_payload(deal)})
    return Response({'estimate': freight.item_logistics(deal)})

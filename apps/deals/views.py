"""Deal views — list/create/detail, items, splits, notes, timeline, totals."""
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.currency import deal_totals
from apps.core.permissions import (
    IsSalesOrAdmin,
    IsSalesOrOperationsOrAdmin,
)

from .models import Deal, DealItem, DealActivity, DealItemSplit
from .serializers import (
    DealListSerializer,
    DealDetailSerializer,
    DealItemSerializer,
    DealActivitySerializer,
    DealItemSplitSerializer,
)
from . import services


# ── Deal list / create ───────────────────────────────────────────────────────

class DealListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = Deal.objects.select_related('client', 'owner').all()

        # Sales users only see deals they own
        if getattr(request.user, 'role', None) == 'sales':
            qs = qs.filter(owner=request.user)

        status_filter = request.query_params.get('status')
        client_filter = request.query_params.get('client')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if client_filter:
            qs = qs.filter(client_id=client_filter)

        return Response(DealListSerializer(qs, many=True).data)

    def post(self, request):
        data = dict(request.data)
        # Default owner to current user
        if not data.get('owner'):
            data['owner'] = str(request.user.id)
        ser = DealDetailSerializer(data=data)
        ser.is_valid(raise_exception=True)
        deal = ser.save()
        DealActivity.objects.create(
            deal=deal, user=request.user,
            activity_type='created',
            description=f'Deal {deal.reference} created',
        )
        return Response(DealDetailSerializer(deal).data,
                        status=status.HTTP_201_CREATED)


class DealDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        return Response(DealDetailSerializer(deal).data)

    def put(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        ser  = DealDetailSerializer(deal, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        DealActivity.objects.create(
            deal=deal, user=request.user,
            activity_type='updated',
            description=f'Deal {deal.reference} updated',
        )
        return Response(ser.data)


# ── Currency, totals, timeline, notes ────────────────────────────────────────

class DealCurrencyView(APIView):
    """POST /api/deals/{id}/currency/ — change currency + exchange rate."""
    permission_classes = [IsSalesOrAdmin]

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        currency = request.data.get('currency')
        rate     = request.data.get('exchange_rate')
        if not currency:
            return Response({'error': 'currency is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        deal.currency = currency
        if rate is not None:
            try:
                deal.exchange_rate = Decimal(str(rate))
            except (ArithmeticError, ValueError):
                return Response({'error': 'exchange_rate invalid'},
                                status=status.HTTP_400_BAD_REQUEST)
        deal.save(update_fields=['currency', 'exchange_rate', 'updated_at'])
        DealActivity.objects.create(
            deal=deal, user=request.user,
            activity_type='currency_changed',
            description=f'Currency set to {currency} @ {deal.exchange_rate}',
        )
        return Response(DealDetailSerializer(deal).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def deal_totals_view(request, pk):
    """GET /api/deals/{id}/totals/"""
    deal = get_object_or_404(Deal, pk=pk)
    # Use parent (non-split-child) items so we don't double-count
    items = DealItem.objects.filter(deal=deal, is_split_child=False)
    rows  = [
        {'qty': i.qty, 'unit_cost': i.unit_cost, 'unit_price': i.unit_price}
        for i in items
    ]
    return Response(deal_totals(rows, deal.currency, deal.exchange_rate))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def deal_timeline(request, pk):
    """GET /api/deals/{id}/timeline/"""
    get_object_or_404(Deal, pk=pk)
    activities = DealActivity.objects.filter(deal_id=pk).select_related('user')
    return Response(DealActivitySerializer(activities, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deal_add_note(request, pk):
    """POST /api/deals/{id}/notes/"""
    deal = get_object_or_404(Deal, pk=pk)
    note = (request.data.get('note') or '').strip()
    if not note:
        return Response({'error': 'note is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    activity = DealActivity.objects.create(
        deal=deal, user=request.user,
        activity_type='note',
        description=note,
    )
    return Response(DealActivitySerializer(activity).data,
                    status=status.HTTP_201_CREATED)


# ── Deal items ───────────────────────────────────────────────────────────────

class DealItemListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        get_object_or_404(Deal, pk=pk)
        items = DealItem.objects.filter(deal_id=pk)
        return Response(DealItemSerializer(items, many=True).data)

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        data = dict(request.data)
        # Auto-set item_number if not provided
        if not data.get('item_number'):
            last = DealItem.objects.filter(
                deal=deal, is_split_child=False,
            ).order_by('-item_number').first()
            data['item_number'] = (last.item_number + 1) if last else 1
        ser = DealItemSerializer(data=data)
        ser.is_valid(raise_exception=True)
        item = ser.save(deal=deal)
        return Response(DealItemSerializer(item).data,
                        status=status.HTTP_201_CREATED)


class DealItemDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [IsSalesOrAdmin()]
        if self.request.method in ('PUT', 'PATCH'):
            return [IsSalesOrOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get_object(self, pk, item_id):
        return DealItem.objects.filter(deal_id=pk, pk=item_id).first()

    def put(self, request, pk, item_id):
        item = self.get_object(pk, item_id)
        if not item:
            return Response({'error': 'Not found'}, status=404)
        ser = DealItemSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk, item_id):
        item = self.get_object(pk, item_id)
        if not item:
            return Response({'error': 'Not found'}, status=404)
        item.delete()
        return Response(status=204)


# ── Deal item splits (awards) ────────────────────────────────────────────────

class DealSplitListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        splits = DealItemSplit.objects.filter(
            parent_item__deal_id=pk,
        ).select_related('supplier_quote__supplier', 'parent_item')
        return Response(DealItemSplitSerializer(splits, many=True).data)

    def post(self, request, pk):
        get_object_or_404(Deal, pk=pk)
        try:
            result = services.split_item_to_supplier(
                parent_item_id    = request.data['parent_item_id'],
                supplier_quote_id = request.data['supplier_quote_id'],
                qty_awarded       = request.data['qty_awarded'],
                unit_cost         = request.data['unit_cost'],
            )
        except (KeyError, ValueError) as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class DealSplitDeleteView(APIView):
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def delete(self, request, pk, parent_item_id, quote_id):
        get_object_or_404(Deal, pk=pk)
        removed = services.remove_item_split(parent_item_id, quote_id)
        if not removed:
            return Response({'error': 'Split not found'}, status=404)
        return Response(status=204)

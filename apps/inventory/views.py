"""Inventory views — stock items, movements, adjustments, delivery deduction."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOperationsOrAdmin
from .models import StockItem
from .serializers import StockItemSerializer
from . import services


class StockListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        items = StockItem.objects.all()
        return Response(StockItemSerializer(items, many=True).data)

    def post(self, request):
        ser = StockItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class StockDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get_object(self, pk):
        return StockItem.objects.filter(pk=pk).first()

    def get(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response({'error': 'Not found'}, status=404)
        return Response(StockItemSerializer(item).data)

    def put(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response({'error': 'Not found'}, status=404)
        ser = StockItemSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


@api_view(['POST'])
@permission_classes([IsOperationsOrAdmin])
def adjust_stock(request, pk):
    """POST /api/inventory/{id}/adjust/ — body: {movement_type, qty, reason, ref}"""
    try:
        result = services.adjust_stock(
            item_id       = pk,
            movement_type = request.data.get('movement_type'),
            qty           = request.data.get('qty'),
            reason        = request.data.get('reason', ''),
            ref           = request.data.get('ref', ''),
            user_id       = request.user.id,
        )
    except ValueError as e:
        return Response({'error': str(e)}, status=400)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stock_history(request, pk):
    """GET /api/inventory/{id}/history/"""
    if not StockItem.objects.filter(pk=pk).exists():
        return Response({'error': 'Not found'}, status=404)
    return Response(services.get_movement_history(pk))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def low_stock(request):
    """GET /api/inventory/low-stock/"""
    return Response(services.get_low_stock_items())


@api_view(['POST'])
@permission_classes([IsOperationsOrAdmin])
def deduct_on_delivery(request, dn_id):
    """POST /api/inventory/deduct/{dn_id}/ — deduct stock for a delivery note."""
    results = services.deduct_stock_on_delivery(dn_id, user_id=request.user.id)
    return Response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_summary(request):
    """GET /api/inventory/summary/"""
    return Response(services.get_stock_summary())

"""Supplier CRUD + stats endpoint."""
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOperationsOrAdmin
from .models import Supplier
from .serializers import SupplierSerializer


class SupplierListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        suppliers = Supplier.objects.all()
        return Response(SupplierSerializer(suppliers, many=True).data)

    def post(self, request):
        ser = SupplierSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class SupplierDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ('PUT', 'DELETE'):
            return [IsOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get_object(self, pk):
        return Supplier.objects.filter(pk=pk).first()

    def get(self, request, pk):
        s = self.get_object(pk)
        if not s:
            return Response({'error': 'Not found'}, status=404)
        return Response(SupplierSerializer(s).data)

    def put(self, request, pk):
        s = self.get_object(pk)
        if not s:
            return Response({'error': 'Not found'}, status=404)
        ser = SupplierSerializer(s, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk):
        s = self.get_object(pk)
        if not s:
            return Response({'error': 'Not found'}, status=404)
        s.delete()
        return Response(status=204)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def supplier_stats(request, pk):
    """
    GET /api/suppliers/{id}/stats/
    Returns: {total_quotes, winning_quotes, deals_quoted, win_rate_pct}
    """
    from apps.quotes.models import SupplierQuote  # lazy import to avoid cycles

    if not Supplier.objects.filter(pk=pk).exists():
        return Response({'error': 'Not found'}, status=404)

    agg = SupplierQuote.objects.filter(supplier_id=pk).aggregate(
        total_quotes=Count('id'),
        winning_quotes=Count('id', filter=Q(selected=True)),
        deals_quoted=Count('deal_id', distinct=True),
    )
    total    = agg.get('total_quotes') or 0
    winning  = agg.get('winning_quotes') or 0
    win_rate = round((winning / total * 100), 1) if total else 0.0

    return Response({
        'total_quotes':   total,
        'winning_quotes': winning,
        'deals_quoted':   agg.get('deals_quoted') or 0,
        'win_rate_pct':   win_rate,
    })

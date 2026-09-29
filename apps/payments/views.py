"""Payments / Accounts Receivable views."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsFinanceOrAdmin
from .models import Payment
from .serializers import PaymentSerializer
from . import services


class ARView(APIView):
    """GET /api/payments/ar/ — list all open invoices with balances."""
    permission_classes = [IsFinanceOrAdmin]

    def get(self, request):
        owner = None
        if getattr(request.user, 'role', None) == 'sales':
            owner = request.user.id
        return Response(services.get_ar_overview(owner_id=owner))


@api_view(['GET'])
@permission_classes([IsFinanceOrAdmin])
def ar_summary(request):
    """GET /api/payments/ar/summary/"""
    return Response(services.get_ar_summary())


@api_view(['GET'])
@permission_classes([IsFinanceOrAdmin])
def ar_overdue(request):
    """GET /api/payments/ar/overdue/?days=30"""
    try:
        days = int(request.query_params.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    return Response(services.get_overdue_invoices(days=days))


@api_view(['GET'])
@permission_classes([IsFinanceOrAdmin])
def invoice_balance(request, invoice_ref):
    """GET /api/payments/balance/{invoice_ref}/"""
    data = services.get_invoice_payment_history(invoice_ref)
    if not data:
        return Response({'error': 'Invoice not found'}, status=404)
    return Response({
        'invoice_ref':    data.get('invoice_ref'),
        'total_invoiced': data.get('total_invoiced'),
        'total_paid':     data.get('total_paid'),
        'balance':        data.get('balance'),
        'currency':       data.get('currency'),
        'due_date':       data.get('due_date'),
        'days_overdue':   data.get('days_overdue'),
    })


@api_view(['GET'])
@permission_classes([IsFinanceOrAdmin])
def invoice_history(request, invoice_ref):
    """GET /api/payments/history/{invoice_ref}/"""
    data = services.get_invoice_payment_history(invoice_ref)
    if not data:
        return Response({'error': 'Invoice not found'}, status=404)
    return Response(data)


class PaymentCreateView(APIView):
    """POST /api/payments/ — record a new payment."""
    permission_classes = [IsFinanceOrAdmin]

    def post(self, request):
        data = dict(request.data)
        ser  = PaymentSerializer(data=data)
        ser.is_valid(raise_exception=True)
        ser.save(recorded_by=request.user)
        return Response(ser.data, status=status.HTTP_201_CREATED)

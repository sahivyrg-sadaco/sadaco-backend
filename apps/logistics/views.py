"""Supplier orders, shipments and the tracking board."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSalesOrOperationsOrAdmin
from apps.deals.models import Deal
from . import services
from .models import Shipment, SupplierOrder
from .serializers import ShipmentSerializer, SupplierOrderSerializer, mark_progress


class _WriteRoles:
    """Reads for anyone signed in; changes for sales, operations and admin."""
    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [IsAuthenticated()]
        return [IsSalesOrOperationsOrAdmin()]


def _orders_qs():
    return (SupplierOrder.objects.select_related('supplier')
            .prefetch_related('items', 'shipments'))


def _ships_qs():
    return Shipment.objects.prefetch_related('orders')


def _sync_cost(shipment):
    """Freight entered on a shipment appears as that shipment's cost on the Costs tab."""
    from apps.costs.services import sync_shipment_cost
    sync_shipment_cost(shipment)


# ── Supplier orders ─────────────────────────────────────────────────────────
class DealOrdersView(_WriteRoles, APIView):
    """GET /api/deals/{id}/orders/ → { orders, pending_awards }"""
    def get(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        orders = list(_orders_qs().filter(deal=deal))
        from apps.finance import gates
        return Response({
            'orders': SupplierOrderSerializer(orders, many=True).data,
            'pending_awards': services.pending_awards(deal),
            # Payment readiness: per order (supplier side) and for the client.
            'payment': {
                'orders': {o.id: gates.order_money(o) for o in orders},
                'client': gates.client_money(deal),
            },
        })


class DealOrdersFromAwardsView(_WriteRoles, APIView):
    """POST /api/deals/{id}/orders/from-awards/ → create draft orders for all pending awards."""
    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        touched = services.create_orders_from_awards(deal, request.user)
        if not touched:
            return Response({'error': 'Every awarded item is already on a supplier order.'},
                            status=status.HTTP_400_BAD_REQUEST)
        orders = _orders_qs().filter(pk__in=[o.pk for o in touched])
        return Response(SupplierOrderSerializer(orders, many=True).data, status=status.HTTP_201_CREATED)


class OrderDetailView(_WriteRoles, APIView):
    """GET/PUT/DELETE /api/orders/{id}/"""
    def get(self, request, oid):
        return Response(SupplierOrderSerializer(get_object_or_404(_orders_qs(), pk=oid)).data)

    @transaction.atomic
    def put(self, request, oid):
        order = get_object_or_404(_orders_qs(), pk=oid)
        old_status = order.status
        ser = SupplierOrderSerializer(order, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        new_status = ser.validated_data.get('status', old_status)
        if new_status != old_status:
            from apps.finance import gates
            blocked = gates.enforce(request, order.deal, gates.for_order_status(order, new_status))
            if blocked:
                return blocked
        order = ser.save()
        if order.status != old_status:
            services.stamp_order_status(order, old_status)
            order.save()
            services.log(order.deal, request.user,
                         f'Supplier order {order.po_number}: {order.get_status_display().lower()}.')
        order = _orders_qs().get(pk=order.pk)
        return Response(SupplierOrderSerializer(order).data)

    def delete(self, request, oid):
        order = get_object_or_404(SupplierOrder, pk=oid)
        if order.status != 'draft':
            return Response({'error': 'Only draft orders can be deleted. Cancel it instead.'},
                            status=status.HTTP_400_BAD_REQUEST)
        services.log(order.deal, request.user, f'Draft supplier order {order.po_number} deleted.')
        order.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Shipments ───────────────────────────────────────────────────────────────
class DealShipmentsView(_WriteRoles, APIView):
    """GET/POST /api/deals/{id}/shipments/"""
    def get(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        return Response(ShipmentSerializer(_ships_qs().filter(deal=deal), many=True).data)

    @transaction.atomic
    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        ser = ShipmentSerializer(data=request.data, context={'deal': deal})
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        from apps.finance import gates
        blocked = gates.enforce(request, deal, gates.for_shipment(
            deal, old_status=None, new_status=v.get('status', 'planned'), mode=v.get('mode', 'courier'),
            tracking=v.get('tracking_number', ''), leg=v.get('leg', 'to_miami'), orders=v.get('orders', [])))
        if blocked:
            return blocked
        shipment = ser.save(deal=deal, created_by=request.user)
        mark_progress(shipment, ['status'])
        services.after_shipment_change(shipment, None, request.user)
        shipment.save()
        _sync_cost(shipment)
        services.log(deal, request.user, f'Shipment added: {shipment.get_leg_display()}'
                     + (f', tracking {shipment.tracking_number}' if shipment.tracking_number else '') + '.')
        return Response(ShipmentSerializer(_ships_qs().get(pk=shipment.pk)).data,
                        status=status.HTTP_201_CREATED)


class ShipmentDetailView(_WriteRoles, APIView):
    """GET/PUT/DELETE /api/shipments/{id}/"""
    def get(self, request, sid):
        return Response(ShipmentSerializer(get_object_or_404(_ships_qs(), pk=sid)).data)

    @transaction.atomic
    def put(self, request, sid):
        shipment = get_object_or_404(_ships_qs(), pk=sid)
        before = {f: getattr(shipment, f) for f in ('status', 'etd', 'eta', 'departed_date',
                                                     'arrived_date', 'tracking_number')}
        ser = ShipmentSerializer(shipment, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        from apps.finance import gates
        blocked = gates.enforce(request, shipment.deal, gates.for_shipment(
            shipment.deal, old_status=shipment.status, new_status=v.get('status', shipment.status),
            mode=v.get('mode', shipment.mode), tracking=v.get('tracking_number', shipment.tracking_number),
            leg=v.get('leg', shipment.leg), orders=v.get('orders', list(shipment.orders.all()))))
        if blocked:
            return blocked
        shipment = ser.save()
        changed = [f for f, v in before.items() if getattr(shipment, f) != v]
        mark_progress(shipment, changed)
        if 'status' in changed or 'orders' in request.data:
            services.after_shipment_change(shipment, before['status'], request.user)
        shipment.save()
        _sync_cost(shipment)
        if 'status' in changed:
            services.log(shipment.deal, request.user,
                         f'Shipment {shipment.get_leg_display()}: {shipment.get_status_display().lower()}.')
        return Response(ShipmentSerializer(_ships_qs().get(pk=shipment.pk)).data)

    @transaction.atomic
    def delete(self, request, sid):
        shipment = get_object_or_404(Shipment, pk=sid)
        from apps.costs.services import detach_shipment
        detach_shipment(shipment)
        services.log(shipment.deal, request.user,
                     f'Shipment deleted: {shipment.get_leg_display()}.')
        shipment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Tracking board ──────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tracking_board(request):
    """GET /api/tracking/board/ → every open order and shipment, most urgent first."""
    return Response(services.build_board(request.user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tracking_attention(request):
    """GET /api/tracking/attention/ → only the entries with reminders."""
    board = services.build_board(request.user)
    board['entries'] = [e for e in board['entries'] if e['flags']]
    return Response(board)

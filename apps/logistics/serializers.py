from django.utils import timezone
from rest_framework import serializers

from .models import Shipment, SupplierOrder, SupplierOrderItem


class SupplierOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SupplierOrderItem
        fields = ['id', 'deal_item', 'item_number', 'description', 'part_number', 'brand',
                  'qty', 'unit', 'unit_cost']
        read_only_fields = fields


class SupplierOrderSerializer(serializers.ModelSerializer):
    supplier_name  = serializers.SerializerMethodField()
    supplier_email = serializers.SerializerMethodField()
    status_label   = serializers.CharField(source='get_status_display', read_only=True)
    items          = SupplierOrderItemSerializer(many=True, read_only=True)
    total          = serializers.SerializerMethodField()
    shipment_ids   = serializers.SerializerMethodField()

    class Meta:
        model  = SupplierOrder
        fields = [
            'id', 'deal', 'supplier', 'supplier_name', 'supplier_email', 'supplier_quote',
            'po_number', 'supplier_ref', 'status', 'status_label', 'currency',
            'payment_terms', 'incoterm',
            'sent_date', 'confirmed_date', 'promised_date', 'ready_date', 'shipped_date', 'received_date',
            'notes', 'items', 'total', 'shipment_ids', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'deal', 'supplier', 'supplier_quote', 'currency',
                            'created_at', 'updated_at']

    def get_supplier_name(self, o):
        return o.supplier.company_name if o.supplier else None

    def get_supplier_email(self, o):
        return o.supplier.email if o.supplier else None

    def get_total(self, o):
        return round(o.total, 2)

    def get_shipment_ids(self, o):
        return [s.id for s in o.shipments.all()]

    def validate_po_number(self, v):
        v = v.strip()
        if not v:
            raise serializers.ValidationError('Enter a PO number.')
        return v


class ShipmentSerializer(serializers.ModelSerializer):
    leg_label     = serializers.CharField(source='get_leg_display', read_only=True)
    mode_label    = serializers.CharField(source='get_mode_display', read_only=True)
    status_label  = serializers.CharField(source='get_status_display', read_only=True)
    orders        = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=SupplierOrder.objects.all())
    order_numbers = serializers.SerializerMethodField()

    class Meta:
        model  = Shipment
        fields = [
            'id', 'deal', 'orders', 'order_numbers', 'leg', 'leg_label', 'mode', 'mode_label',
            'origin', 'destination', 'forwarder', 'carrier', 'tracking_number',
            'status', 'status_label', 'etd', 'eta', 'departed_date', 'arrived_date',
            'packages', 'freight_cost', 'freight_currency', 'notes',
            'created_at', 'updated_at', 'last_update_at',
        ]
        read_only_fields = ['id', 'deal', 'created_at', 'updated_at', 'last_update_at']

    def get_order_numbers(self, s):
        return [o.po_number for o in s.orders.all()]

    def validate_orders(self, orders):
        deal = self.context.get('deal') or (self.instance.deal if self.instance else None)
        for o in orders:
            if deal and o.deal_id != deal.id:
                raise serializers.ValidationError(f'{o.po_number} belongs to another deal.')
        return orders

    def validate(self, attrs):
        etd = attrs.get('etd', getattr(self.instance, 'etd', None))
        eta = attrs.get('eta', getattr(self.instance, 'eta', None))
        if etd and eta and eta < etd:
            raise serializers.ValidationError({'eta': 'The ETA is before the departure date.'})
        return attrs


PROGRESS_FIELDS = {'status', 'etd', 'eta', 'departed_date', 'arrived_date', 'tracking_number'}


def mark_progress(shipment, changed_fields):
    if PROGRESS_FIELDS & set(changed_fields):
        shipment.last_update_at = timezone.now()

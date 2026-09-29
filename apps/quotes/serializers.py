from rest_framework import serializers
from .models import SupplierQuote, SupplierQuoteItem


class SupplierQuoteItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SupplierQuoteItem
        fields = ['id', 'quote', 'deal_item',
                  'unit_price', 'total_price', 'notes']
        read_only_fields = ['id', 'total_price']
        extra_kwargs = {
            'unit_price':  {'coerce_to_string': False},
            'total_price': {'coerce_to_string': False},
        }


class SupplierQuoteSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(
        source='supplier.company_name', read_only=True, default=None,
    )
    items = SupplierQuoteItemSerializer(many=True, read_only=True)

    class Meta:
        model  = SupplierQuote
        fields = [
            'id', 'deal', 'supplier', 'supplier_name',
            'supplier_ref', 'payment_terms', 'incoterm',
            'lead_time_days', 'selected', 'created_at', 'items',
        ]
        read_only_fields = ['id', 'created_at', 'items']

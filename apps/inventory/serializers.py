from rest_framework import serializers
from .models import StockItem, StockMovement


class StockItemSerializer(serializers.ModelSerializer):
    qty_available = serializers.SerializerMethodField()
    is_low_stock  = serializers.SerializerMethodField()

    class Meta:
        model  = StockItem
        fields = [
            'id', 'sku', 'description', 'unit',
            'qty_on_hand', 'qty_reserved', 'reorder_point',
            'qty_available', 'is_low_stock', 'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']
        extra_kwargs = {
            'qty_on_hand':   {'coerce_to_string': False},
            'qty_reserved':  {'coerce_to_string': False},
            'reorder_point': {'coerce_to_string': False},
        }

    def get_qty_available(self, obj):
        return obj.qty_available

    def get_is_low_stock(self, obj):
        return obj.is_low_stock


class StockMovementSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source='created_by.name', read_only=True, default=None,
    )

    class Meta:
        model  = StockMovement
        fields = [
            'id', 'stock_item', 'movement_type', 'qty',
            'ref', 'reason', 'created_by', 'user_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'qty': {'coerce_to_string': False}}

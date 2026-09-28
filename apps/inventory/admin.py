from django.contrib import admin
from .models import StockItem, StockMovement


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display  = ('sku', 'description', 'qty_on_hand',
                     'qty_reserved', 'reorder_point', 'updated_at')
    search_fields = ('sku', 'description')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('id', 'stock_item', 'movement_type', 'qty',
                    'ref', 'created_by', 'created_at')
    list_filter  = ('movement_type',)
    search_fields = ('ref', 'reason')

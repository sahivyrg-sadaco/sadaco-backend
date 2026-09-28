from django.contrib import admin
from .models import Deal, DealItem, DealItemSplit, DealActivity


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display  = ('reference', 'client', 'owner', 'status',
                     'deal_status', 'currency', 'created_at')
    list_filter   = ('status', 'deal_status', 'currency', 'seller_entity')
    search_fields = ('reference', 'client_ref', 'client__full_name')
    date_hierarchy = 'created_at'


@admin.register(DealItem)
class DealItemAdmin(admin.ModelAdmin):
    list_display  = ('id', 'deal', 'item_number', 'description',
                     'qty', 'unit_cost', 'unit_price', 'is_split_child')
    list_filter   = ('is_split_child',)
    search_fields = ('description', 'part_number', 'brand')


@admin.register(DealItemSplit)
class DealItemSplitAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent_item', 'supplier_quote',
                    'qty_awarded', 'unit_cost', 'created_at')


@admin.register(DealActivity)
class DealActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'deal', 'activity_type', 'user', 'created_at')
    list_filter  = ('activity_type',)

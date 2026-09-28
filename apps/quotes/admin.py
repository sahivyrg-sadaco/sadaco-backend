from django.contrib import admin
from .models import SupplierQuote, SupplierQuoteItem


@admin.register(SupplierQuote)
class SupplierQuoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'deal', 'supplier', 'supplier_ref',
                    'selected', 'created_at')
    list_filter  = ('selected',)


@admin.register(SupplierQuoteItem)
class SupplierQuoteItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'quote', 'deal_item', 'unit_price', 'total_price')

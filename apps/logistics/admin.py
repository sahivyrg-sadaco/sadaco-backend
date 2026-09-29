from django.contrib import admin

from .models import Shipment, SupplierOrder, SupplierOrderItem


class SupplierOrderItemInline(admin.TabularInline):
    model = SupplierOrderItem
    extra = 0


@admin.register(SupplierOrder)
class SupplierOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'deal', 'supplier', 'status', 'promised_date')
    list_filter  = ('status',)
    inlines      = [SupplierOrderItemInline]


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('deal', 'leg', 'mode', 'status', 'tracking_number', 'eta')
    list_filter  = ('status', 'leg', 'mode')

from django.contrib import admin

from .models import SupplierRFQ


@admin.register(SupplierRFQ)
class SupplierRFQAdmin(admin.ModelAdmin):
    list_display = ('deal', 'supplier', 'status', 'sent_date', 'reply_by', 'followup_count')
    list_filter  = ('status',)

from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ('invoice_ref', 'amount', 'currency',
                     'payment_date', 'method', 'recorded_by', 'created_at')
    list_filter   = ('currency', 'method')
    search_fields = ('invoice_ref', 'notes')
    date_hierarchy = 'payment_date'

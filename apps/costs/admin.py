from django.contrib import admin

from .models import DealCost


@admin.register(DealCost)
class DealCostAdmin(admin.ModelAdmin):
    list_display = ('deal', 'category', 'description', 'estimate_amount', 'actual_amount', 'currency')
    list_filter  = ('category',)

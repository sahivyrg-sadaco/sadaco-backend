from django.contrib import admin
from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display  = ('company_name', 'country', 'contact_name', 'email', 'created_at')
    list_filter   = ('country',)
    search_fields = ('company_name', 'contact_name', 'email')
    ordering      = ('company_name',)

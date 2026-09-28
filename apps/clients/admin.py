from django.contrib import admin
from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display  = ('dropdown_name', 'code', 'full_name', 'country', 'created_at')
    list_filter   = ('country', 'currency')
    search_fields = ('dropdown_name', 'full_name', 'code')
    ordering      = ('full_name',)

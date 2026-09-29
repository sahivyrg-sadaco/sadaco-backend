from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display  = ('email', 'name', 'role', 'lang', 'is_active', 'created_at')
    list_filter   = ('role', 'is_active', 'lang')
    search_fields = ('email', 'name')
    ordering      = ('name',)

from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'type', 'title', 'read', 'created_at')
    list_filter   = ('type', 'read')
    search_fields = ('title', 'body')

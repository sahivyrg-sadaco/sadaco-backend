from django.contrib import admin
from .models import (
    FileAttachment, InvoicedItem, DeliveryNote, DeliveryNoteItem, Asset,
)


@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display  = ('file_name', 'doc_type', 'deal', 'client',
                     'generated_by', 'uploaded_at')
    list_filter   = ('doc_type',)
    search_fields = ('file_name', 'drive_file_id')


@admin.register(InvoicedItem)
class InvoicedItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'deal', 'deal_item', 'invoice_ref',
                    'qty_invoiced', 'created_at')
    search_fields = ('invoice_ref',)


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display  = ('reference', 'deal', 'invoice_ref',
                     'sequence', 'receiver_name', 'created_at')
    search_fields = ('reference', 'invoice_ref')


@admin.register(DeliveryNoteItem)
class DeliveryNoteItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'delivery_note', 'deal_item', 'qty_delivered')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('key', 'mime_type', 'updated_at')

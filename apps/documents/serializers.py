from rest_framework import serializers
from .models import (
    FileAttachment, InvoicedItem, DeliveryNote, DeliveryNoteItem,
)


class FileAttachmentSerializer(serializers.ModelSerializer):
    generated_by_name = serializers.CharField(
        source='generated_by.name', read_only=True, default=None,
    )

    class Meta:
        model  = FileAttachment
        fields = [
            'id', 'drive_file_id', 'file_name', 'web_view_link',
            'drive_folder_id', 'mime_type', 'file_size_bytes',
            'deal', 'client', 'doc_type',
            'generated_by', 'generated_by_name', 'uploaded_at',
        ]
        read_only_fields = [
            'id', 'drive_file_id', 'web_view_link', 'drive_folder_id',
            'mime_type', 'file_size_bytes', 'uploaded_at',
        ]


class InvoicedItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InvoicedItem
        fields = '__all__'
        extra_kwargs = {'qty_invoiced': {'coerce_to_string': False}}


class DeliveryNoteItemSerializer(serializers.ModelSerializer):
    item_description = serializers.CharField(
        source='deal_item.description', read_only=True,
    )

    class Meta:
        model  = DeliveryNoteItem
        fields = ['id', 'delivery_note', 'deal_item',
                  'qty_delivered', 'item_description']
        extra_kwargs = {'qty_delivered': {'coerce_to_string': False}}


class DeliveryNoteSerializer(serializers.ModelSerializer):
    items           = DeliveryNoteItemSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.name', read_only=True, default=None,
    )

    class Meta:
        model  = DeliveryNote
        fields = [
            'id', 'deal', 'invoice_ref', 'sequence', 'reference',
            'receiver_name', 'notes',
            'created_by', 'created_by_name', 'created_at', 'items',
        ]
        read_only_fields = ['id', 'created_at', 'reference']

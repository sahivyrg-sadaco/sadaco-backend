"""
Central tables for all files (Drive-hosted), invoicing, and delivery notes.
"""
from django.db import models


DOC_TYPE_CHOICES = [
    ('Quote',          'Quote'),
    ('PO',             'PO'),
    ('Invoice',        'Invoice'),
    ('Delivery Note',  'Delivery Note'),
    ('Attachment',     'Attachment'),
]


class FileAttachment(models.Model):
    """One row per file stored in Google Drive."""
    drive_file_id   = models.CharField(max_length=200, unique=True)
    file_name       = models.CharField(max_length=500)
    web_view_link   = models.URLField(max_length=1000)
    drive_folder_id = models.CharField(max_length=200, blank=True)
    mime_type       = models.CharField(max_length=100, blank=True)
    file_size_bytes = models.BigIntegerField(null=True, blank=True)

    deal            = models.ForeignKey(
        'deals.Deal', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='attachments',
    )
    client          = models.ForeignKey(
        'clients.Client', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='attachments',
    )

    doc_type        = models.CharField(
        max_length=50, choices=DOC_TYPE_CHOICES, default='Attachment',
    )
    generated_by    = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    uploaded_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'file_attachments'
        ordering = ['-uploaded_at']


class InvoicedItem(models.Model):
    """Records that a DealItem has been invoiced under an invoice_ref."""
    deal         = models.ForeignKey('deals.Deal',       on_delete=models.CASCADE)
    deal_item    = models.ForeignKey('deals.DealItem',   on_delete=models.CASCADE)
    invoice_ref  = models.CharField(max_length=200, db_index=True)
    qty_invoiced = models.DecimalField(max_digits=18, decimal_places=4)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'invoiced_items'


class DeliveryNote(models.Model):
    deal          = models.ForeignKey('deals.Deal', on_delete=models.CASCADE)
    invoice_ref   = models.CharField(max_length=200)
    sequence      = models.IntegerField(default=1)
    reference     = models.CharField(max_length=200, unique=True)
    receiver_name = models.CharField(max_length=200, blank=True)
    notes         = models.TextField(blank=True)
    created_by    = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'delivery_notes'
        ordering = ['-created_at']


class DeliveryNoteItem(models.Model):
    delivery_note = models.ForeignKey(
        DeliveryNote, on_delete=models.CASCADE, related_name='items',
    )
    deal_item     = models.ForeignKey('deals.DealItem', on_delete=models.CASCADE)
    qty_delivered = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        db_table = 'delivery_note_items'


class Asset(models.Model):
    """Binary assets (logos, signatures, etc.) keyed by string name."""
    key        = models.CharField(max_length=100, primary_key=True)
    mime_type  = models.CharField(max_length=100, default='image/png')
    data       = models.BinaryField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assets'

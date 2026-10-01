"""
Quotes we send to clients, and the purchase orders they answer with.

A ClientQuote is a snapshot: the lines, charges, totals and terms exactly as
sent, so later edits to the deal don't change what the client received.
Changing prices means a new version (Q2, Q3…); the old one is superseded.

A ClientPO is the client's purchase order. It must be processed (checked
against the quote) before supplier orders can be placed.
"""
from django.db import models


class ClientQuote(models.Model):
    STATUS_CHOICES = [
        ('draft',      'Draft'),
        ('sent',       'Sent'),
        ('accepted',   'Accepted'),
        ('declined',   'Declined'),
        ('superseded', 'Replaced by a newer version'),
    ]

    deal           = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='client_quotes')
    version        = models.IntegerField()
    number         = models.CharField(max_length=60, unique=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    language       = models.CharField(max_length=5, default='es')
    issue_date     = models.DateField()
    valid_until    = models.DateField()
    currency       = models.CharField(max_length=10, default='USD')

    # Snapshot, as sent.
    lines          = models.JSONField(default=list)    # [{n, description, part_number, brand, model, qty, unit, unit_price, total}]
    charges        = models.JSONField(default=list)    # [{label, amount}]
    total          = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    payment_terms  = models.CharField(max_length=300, blank=True)
    incoterm       = models.CharField(max_length=20, blank=True)
    delivery_point = models.CharField(max_length=200, blank=True)
    delivery_time  = models.CharField(max_length=200, blank=True)
    client_ref     = models.CharField(max_length=200, blank=True)
    notes          = models.TextField(blank=True)       # shown to the client

    sent_date      = models.DateField(null=True, blank=True)
    sent_to        = models.CharField(max_length=300, blank=True)
    subject        = models.CharField(max_length=300, blank=True)
    body           = models.TextField(blank=True)
    followup_count = models.IntegerField(default=0)
    last_followup_date = models.DateField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)

    created_by     = models.ForeignKey('accounts.User', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_quotes'
        ordering = ['deal_id', '-version']

    def __str__(self):
        return self.number


class ClientPO(models.Model):
    STATUS_CHOICES = [
        ('received',  'Received, to process'),
        ('processed', 'Processed'),
        ('rejected',  'Rejected'),
    ]

    deal          = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='client_pos')
    quote         = models.ForeignKey(ClientQuote, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='purchase_orders')
    po_number     = models.CharField(max_length=100)
    po_date       = models.DateField()
    received_date = models.DateField()
    amount        = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency      = models.CharField(max_length=10, default='USD')
    attachment_id = models.IntegerField(null=True, blank=True)   # documents.FileAttachment, when uploaded
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    checks        = models.JSONField(default=dict)               # what was confirmed when processing
    notes         = models.TextField(blank=True)
    reject_reason = models.TextField(blank=True)
    processed_by  = models.ForeignKey('accounts.User', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='+')
    processed_at  = models.DateTimeField(null=True, blank=True)
    created_by    = models.ForeignKey('accounts.User', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='+')
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'client_purchase_orders'
        ordering = ['deal_id', '-received_date', '-id']

    def __str__(self):
        return self.po_number

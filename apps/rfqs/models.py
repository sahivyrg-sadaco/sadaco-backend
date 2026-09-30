"""
Requests for quotation (RFQs) sent to suppliers.

One RFQ = one supplier asked about some of a deal's line items. It stores
the email as sent, when it went out, when a reply is expected, reminders
sent, and the supplier quote that answered it.
"""
from django.db import models


class SupplierRFQ(models.Model):
    STATUS_CHOICES = [
        ('awaiting', 'Awaiting reply'),
        ('replied',  'Quote received'),
        ('declined', 'Declined'),
        ('closed',   'Closed without reply'),
    ]

    deal            = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='rfqs')
    supplier        = models.ForeignKey('suppliers.Supplier', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='rfqs')
    deal_items      = models.ManyToManyField('deals.DealItem', blank=True, related_name='rfqs')
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='awaiting')

    language        = models.CharField(max_length=5, default='en')
    sent_to         = models.CharField(max_length=300, blank=True)
    subject         = models.CharField(max_length=300, blank=True)
    body            = models.TextField(blank=True)

    sent_date       = models.DateField()
    reply_by        = models.DateField(null=True, blank=True)
    replied_date    = models.DateField(null=True, blank=True)
    supplier_quote  = models.ForeignKey('quotes.SupplierQuote', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='rfqs')

    followup_count     = models.IntegerField(default=0)
    last_followup_date = models.DateField(null=True, blank=True)
    notes           = models.TextField(blank=True)

    created_by      = models.ForeignKey('accounts.User', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='+')
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'supplier_rfqs'
        ordering = ['deal_id', '-sent_date', '-id']

    def __str__(self):
        return f'RFQ to {self.supplier or "?"} on {self.sent_date}'

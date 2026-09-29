"""Supplier quotes and quote line items."""
from django.db import models


class SupplierQuote(models.Model):
    deal           = models.ForeignKey(
        'deals.Deal', on_delete=models.CASCADE, related_name='quotes',
    )
    supplier       = models.ForeignKey(
        'suppliers.Supplier', null=True, blank=True, on_delete=models.SET_NULL,
    )
    supplier_ref   = models.CharField(max_length=200, blank=True)
    payment_terms  = models.CharField(max_length=100, blank=True)
    incoterm       = models.CharField(max_length=20,  blank=True)
    lead_time_days = models.IntegerField(null=True, blank=True)
    selected       = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'supplier_quotes'
        ordering = ['-created_at']

    def __str__(self):
        return f'Quote #{self.pk} — {self.supplier or "unassigned"}'


class SupplierQuoteItem(models.Model):
    quote       = models.ForeignKey(
        SupplierQuote, on_delete=models.CASCADE, related_name='items',
    )
    deal_item   = models.ForeignKey(
        'deals.DealItem', on_delete=models.CASCADE,
    )
    unit_price  = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    notes       = models.TextField(blank=True)

    class Meta:
        db_table = 'supplier_quote_items'
        unique_together = [('quote', 'deal_item')]

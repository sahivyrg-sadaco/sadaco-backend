"""Deals, line items, splits, and activity log."""
from django.db import models


PIPELINE_STAGE_CHOICES = [(s, s) for s in [
    'Quoting', 'Negotiating', "Client's PO Received",
    'PO Sent', 'Invoiced', 'Delivered', 'Closed', 'Cancelled',
]]

DEAL_STATUS_CHOICES = [
    ('active',  'Active'),
    ('won',     'Won'),
    ('lost',    'Lost'),
    ('on_hold', 'On Hold'),
]


class Deal(models.Model):
    reference     = models.CharField(max_length=50, unique=True, blank=True)
    client        = models.ForeignKey(
        'clients.Client', on_delete=models.PROTECT, related_name='deals',
    )
    owner         = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='owned_deals',
    )
    seller_entity = models.CharField(max_length=200)
    status        = models.CharField(
        max_length=50, choices=PIPELINE_STAGE_CHOICES, default='Quoting',
    )
    deal_status   = models.CharField(
        max_length=20, choices=DEAL_STATUS_CHOICES, default='active',
    )
    lost_reason   = models.TextField(blank=True)
    currency      = models.CharField(max_length=10, default='USD')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=4, default=1)
    incoterm      = models.CharField(max_length=20,  blank=True)
    port_location = models.CharField(max_length=200, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)
    delivery_time = models.CharField(max_length=200, blank=True)
    client_ref    = models.CharField(max_length=200, blank=True, default='xxx-xxx')
    notes         = models.TextField(blank=True)
    drive_folder_id = models.CharField(max_length=200, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deals'
        ordering = ['-created_at']

    def __str__(self):
        return self.reference or f'Deal #{self.pk}'

    def save(self, *args, **kwargs):
        # Auto-generate reference: {client.code}-{sequence:04d}
        if not self.pk and not self.reference:
            existing = Deal.objects.filter(client=self.client).count()
            self.reference = f'{self.client.code}-{existing + 1:04d}'
        super().save(*args, **kwargs)


class DealItem(models.Model):
    deal         = models.ForeignKey(
        Deal, on_delete=models.CASCADE, related_name='items',
    )
    item_number  = models.IntegerField()
    description  = models.TextField()
    part_number  = models.CharField(max_length=200, blank=True)
    brand        = models.CharField(max_length=200, blank=True)
    model_name   = models.CharField(max_length=200, blank=True, db_column='model')
    qty          = models.DecimalField(max_digits=18, decimal_places=4)
    unit         = models.CharField(max_length=50, blank=True)
    unit_cost    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    margin_pct   = models.DecimalField(max_digits=8,  decimal_places=4, default=0.50)   # company policy
    unit_price   = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    parent_item  = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE, related_name='split_children',
        db_column='parent_item_id',
    )
    awarded_quote = models.ForeignKey(
        'quotes.SupplierQuote', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='awarded_items',
        db_column='awarded_quote_id',
    )
    is_split_child = models.BooleanField(default=False)

    class Meta:
        db_table = 'deal_items'
        ordering = ['deal_id', 'item_number', 'id']

    @property
    def total_cost(self):
        return float(self.qty) * float(self.unit_cost)

    @property
    def total_price(self):
        return float(self.qty) * float(self.unit_price)


class DealItemSplit(models.Model):
    """
    Records an award of N units of a parent DealItem to a specific
    supplier quote. A child DealItem (is_split_child=True) is created
    alongside this row to represent the awarded portion in reports.
    """
    parent_item    = models.ForeignKey(
        DealItem, on_delete=models.CASCADE, related_name='splits',
    )
    supplier_quote = models.ForeignKey(
        'quotes.SupplierQuote', on_delete=models.CASCADE,
    )
    qty_awarded    = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost      = models.DecimalField(max_digits=18, decimal_places=4)
    child_item     = models.ForeignKey(
        DealItem, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='as_child_split',
    )
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'deal_item_splits'
        unique_together = [('parent_item', 'supplier_quote')]


class DealActivity(models.Model):
    deal          = models.ForeignKey(
        Deal, on_delete=models.CASCADE, related_name='activities',
    )
    user          = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
    )
    activity_type = models.CharField(max_length=50)
    description   = models.TextField()
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'deal_activities'
        ordering = ['-created_at']

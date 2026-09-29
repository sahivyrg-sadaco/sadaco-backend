"""
Supplier orders (our POs to suppliers) and shipments.

A supplier order is created from the awards on a deal: one order per
supplier quote, listing the awarded quantities. A shipment is one leg of
the journey (supplier → Miami, Miami → Venezuelan port, port → client,
or direct) and can carry one or more supplier orders from the same deal.
"""
from django.db import models


class SupplierOrder(models.Model):
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('sent',      'Sent to supplier'),
        ('confirmed', 'Confirmed by supplier'),
        ('ready',     'Ready to ship'),
        ('shipped',   'Shipped'),
        ('received',  'Received'),
        ('cancelled', 'Cancelled'),
    ]
    # Which date field is stamped when an order reaches each status.
    STATUS_DATE_FIELD = {
        'sent':      'sent_date',
        'confirmed': 'confirmed_date',
        'ready':     'ready_date',
        'shipped':   'shipped_date',
        'received':  'received_date',
    }
    OPEN_STATUSES = ('draft', 'sent', 'confirmed', 'ready', 'shipped')

    deal           = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='supplier_orders')
    supplier       = models.ForeignKey('suppliers.Supplier', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='orders')
    supplier_quote = models.ForeignKey('quotes.SupplierQuote', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='orders')
    po_number      = models.CharField(max_length=60, unique=True,
                                      error_messages={'unique': 'Another supplier order already uses this PO number.'})
    supplier_ref   = models.CharField(max_length=200, blank=True)   # their order confirmation no.
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    currency       = models.CharField(max_length=10, default='USD')
    payment_terms  = models.CharField(max_length=100, blank=True)
    incoterm       = models.CharField(max_length=20, blank=True)

    sent_date      = models.DateField(null=True, blank=True)
    confirmed_date = models.DateField(null=True, blank=True)
    promised_date  = models.DateField(null=True, blank=True)        # supplier's promised ready/ship date
    ready_date     = models.DateField(null=True, blank=True)
    shipped_date   = models.DateField(null=True, blank=True)
    received_date  = models.DateField(null=True, blank=True)

    notes          = models.TextField(blank=True)
    created_by     = models.ForeignKey('accounts.User', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'supplier_orders'
        ordering = ['deal_id', 'id']

    def __str__(self):
        return self.po_number

    @property
    def total(self):
        return sum(float(i.qty) * float(i.unit_cost) for i in self.items.all())


class SupplierOrderItem(models.Model):
    """A snapshot of one awarded line, so later edits to the deal don't rewrite the PO."""
    order       = models.ForeignKey(SupplierOrder, on_delete=models.CASCADE, related_name='items')
    deal_item   = models.ForeignKey('deals.DealItem', null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='order_lines')
    item_number = models.IntegerField(default=0)
    description = models.TextField()
    part_number = models.CharField(max_length=200, blank=True)
    brand       = models.CharField(max_length=200, blank=True)
    qty         = models.DecimalField(max_digits=18, decimal_places=4)
    unit        = models.CharField(max_length=50, blank=True)
    unit_cost   = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        db_table = 'supplier_order_items'
        ordering = ['order_id', 'item_number', 'id']


class Shipment(models.Model):
    LEG_CHOICES = [
        ('to_miami', 'Supplier to Miami'),
        ('export',   'Miami to Venezuela'),
        ('delivery', 'Port to client'),
        ('direct',   'Supplier direct to client'),
        ('other',    'Other'),
    ]
    MODE_CHOICES = [
        ('air',     'Air'),
        ('ocean',   'Ocean'),
        ('courier', 'Courier'),
        ('truck',   'Truck'),
    ]
    STATUS_CHOICES = [
        ('planned',    'Planned'),
        ('booked',     'Booked'),
        ('in_transit', 'In transit'),
        ('customs',    'In customs'),
        ('arrived',    'Arrived'),
        ('cancelled',  'Cancelled'),
    ]
    OPEN_STATUSES = ('planned', 'booked', 'in_transit', 'customs')

    deal             = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='shipments')
    orders           = models.ManyToManyField(SupplierOrder, blank=True, related_name='shipments')
    leg              = models.CharField(max_length=20, choices=LEG_CHOICES, default='to_miami')
    mode             = models.CharField(max_length=20, choices=MODE_CHOICES, default='courier')
    origin           = models.CharField(max_length=200, blank=True)
    destination      = models.CharField(max_length=200, blank=True)
    forwarder        = models.CharField(max_length=200, blank=True)
    carrier          = models.CharField(max_length=200, blank=True)
    tracking_number  = models.CharField(max_length=200, blank=True)   # tracking / AWB / BL
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')

    etd              = models.DateField(null=True, blank=True)   # estimated departure
    eta              = models.DateField(null=True, blank=True)   # estimated arrival
    departed_date    = models.DateField(null=True, blank=True)
    arrived_date     = models.DateField(null=True, blank=True)

    packages         = models.CharField(max_length=200, blank=True)   # e.g. "3 boxes, 42 kg"
    freight_cost     = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    freight_currency = models.CharField(max_length=10, default='USD')
    notes            = models.TextField(blank=True)

    created_by       = models.ForeignKey('accounts.User', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='+')
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)
    # Last time someone recorded progress (status or dates). Drives "no update" reminders.
    last_update_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'shipments'
        ordering = ['deal_id', 'id']

    def __str__(self):
        return f'{self.get_leg_display()} ({self.tracking_number or "no tracking"})'

from django.db import models


class StockItem(models.Model):
    sku           = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description   = models.CharField(max_length=500)
    unit          = models.CharField(max_length=50, blank=True)
    qty_on_hand   = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    qty_reserved  = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    reorder_point = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_items'
        ordering = ['description']

    def __str__(self):
        return f'{self.sku or "-"}: {self.description}'

    @property
    def qty_available(self):
        return float(self.qty_on_hand) - float(self.qty_reserved)

    @property
    def is_low_stock(self):
        return (float(self.qty_on_hand) <= float(self.reorder_point)
                and float(self.reorder_point) > 0)


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in',         'In'),
        ('out',        'Out'),
        ('adjustment', 'Adjustment'),
    ]

    stock_item    = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name='movements',
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    qty           = models.DecimalField(max_digits=18, decimal_places=4)
    ref           = models.CharField(max_length=200, blank=True)
    reason        = models.TextField(blank=True)
    created_by    = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_movements'
        ordering = ['-created_at']

"""
Extra costs on a deal: everything Sadaco pays besides the goods themselves
(freight, forwarder, customs, duties, bank fees…).

Each cost has an estimate (used when quoting) and an actual (from the
invoice). A cost is either a fixed amount or a percentage of a base
(goods cost, sell value, or CIF value), which is how duties and insurance
are usually charged. Amounts can be in any currency with their own rate.
"""
from django.db import models

CATEGORIES = [
    ('supplier_charges', 'Supplier charges'),
    ('freight_miami',    'Freight to Miami'),
    ('forwarder',        'Forwarder and Miami warehouse'),
    ('freight_intl',     'International freight'),
    ('insurance',        'Cargo insurance'),
    ('customs_broker',   'Customs broker'),
    ('duties',           'Duties and import taxes'),
    ('port_charges',     'Port charges'),
    ('local_delivery',   'Local delivery in Venezuela'),
    ('documents',        'Documents and inspections'),
    ('bank',             'Bank and LC fees'),
    ('commission',       'Commissions'),
    ('other',            'Other'),
]

TREATMENTS = [
    ('included', 'Built into item prices'),
    ('separate', 'Separate line on quote and invoice'),
    ('absorbed', 'Our cost only'),
]

PERCENT_BASES = [
    ('goods_cost', 'Goods cost'),
    ('sell_value', 'Sell value'),
    ('cif_value',  'CIF value'),
]


class DealCost(models.Model):
    deal           = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='extra_costs')
    category       = models.CharField(max_length=30, choices=CATEGORIES)
    description    = models.CharField(max_length=300, blank=True)
    payee          = models.CharField(max_length=200, blank=True)

    amount_type    = models.CharField(max_length=10, default='fixed',
                                      choices=[('fixed', 'Fixed amount'), ('percent', 'Percentage')])
    percent        = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    percent_base   = models.CharField(max_length=20, choices=PERCENT_BASES, blank=True)
    estimate_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    actual_amount  = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency       = models.CharField(max_length=10, default='USD')
    # Same convention as deals: 1 USD = fx_rate units of this cost's currency.
    fx_rate        = models.DecimalField(max_digits=18, decimal_places=6, default=1)

    # How the client sees it. Blank = the deal's default.
    client_treatment = models.CharField(max_length=10, choices=TREATMENTS, blank=True)
    # For separate lines: what we bill the client (in the deal's currency), if not the estimate.
    charge_amount  = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    invoice_ref    = models.CharField(max_length=100, blank=True)
    invoice_date   = models.DateField(null=True, blank=True)
    overrun_acknowledged = models.BooleanField(default=False)
    notes          = models.TextField(blank=True)

    # Where the cost came from, when it was created automatically.
    shipment       = models.ForeignKey('logistics.Shipment', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='costs')
    supplier_order = models.ForeignKey('logistics.SupplierOrder', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='costs')

    created_by     = models.ForeignKey('accounts.User', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deal_costs'
        ordering = ['deal_id', 'id']

    def __str__(self):
        return f'{self.get_category_display()}: {self.description or ""}'


class DealCostSettings(models.Model):
    """Per-deal choice of how extra costs reach the client, when not derived from the incoterm."""
    deal              = models.OneToOneField('deals.Deal', on_delete=models.CASCADE, related_name='cost_settings')
    default_treatment = models.CharField(max_length=10, choices=TREATMENTS)

    class Meta:
        db_table = 'deal_cost_settings'

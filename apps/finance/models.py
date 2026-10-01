"""
Money in and out of a deal.

- ClientInvoice: what we bill the client. A deal can have several (e.g. a
  30% advance and a 70% balance). Client payments are the existing
  payments.Payment records, matched by invoice number.
- Payable: what we owe. Either a supplier's invoice for goods (linked to a
  supplier order) or an extra cost's invoice (linked to a deal cost, created
  automatically when the cost's invoice is recorded).
- PayablePayment: a payment made against a payable.
"""
from django.db import models


class ClientInvoice(models.Model):
    deal         = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='client_invoices')
    number       = models.CharField(max_length=60, unique=True,
                                    error_messages={'unique': 'Another invoice already uses this number.'})
    description  = models.CharField(max_length=200, blank=True)
    invoice_date = models.DateField()
    due_date     = models.DateField()
    amount       = models.DecimalField(max_digits=18, decimal_places=2)
    currency     = models.CharField(max_length=10, default='USD')
    cancelled    = models.BooleanField(default=False)
    notes        = models.TextField(blank=True)
    created_by   = models.ForeignKey('accounts.User', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_invoices'
        ordering = ['deal_id', 'invoice_date', 'id']

    def __str__(self):
        return self.number


class Payable(models.Model):
    KIND_CHOICES = [('goods', 'Supplier invoice'), ('cost', 'Cost invoice')]

    deal           = models.ForeignKey('deals.Deal', on_delete=models.CASCADE, related_name='payables')
    kind           = models.CharField(max_length=10, choices=KIND_CHOICES, default='goods')
    supplier       = models.ForeignKey('suppliers.Supplier', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='payables')
    payee          = models.CharField(max_length=200, blank=True)
    supplier_order = models.ForeignKey('logistics.SupplierOrder', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='payables')
    deal_cost      = models.OneToOneField('costs.DealCost', null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name='payable')
    invoice_ref    = models.CharField(max_length=100, blank=True)
    invoice_date   = models.DateField()
    due_date       = models.DateField()
    amount         = models.DecimalField(max_digits=18, decimal_places=2)
    currency       = models.CharField(max_length=10, default='USD')
    payment_terms  = models.CharField(max_length=100, blank=True)
    notes          = models.TextField(blank=True)
    created_by     = models.ForeignKey('accounts.User', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payables'
        ordering = ['deal_id', 'due_date', 'id']

    def __str__(self):
        return f'{self.payee} {self.invoice_ref}'


class PayablePayment(models.Model):
    payable      = models.ForeignKey(Payable, on_delete=models.CASCADE, related_name='payments')
    amount       = models.DecimalField(max_digits=18, decimal_places=2)
    payment_date = models.DateField()
    method       = models.CharField(max_length=100, blank=True)
    reference    = models.CharField(max_length=100, blank=True)
    notes        = models.TextField(blank=True)
    recorded_by  = models.ForeignKey('accounts.User', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payable_payments'
        ordering = ['payment_date', 'id']


class PaymentPlan(models.Model):
    """
    A payment schedule. Exactly one owner is set:
      supplier / client       → their usual terms (the credit they give or get)
      supplier_order / deal   → the terms for that one order or deal

    steps: [{"pct": 50, "when": "on_order"}, {"pct": 50, "when": "after_shipping", "days": 30}]
    when ∈ on_order | before_shipping | after_shipping | on_delivery
    """
    supplier       = models.OneToOneField('suppliers.Supplier', null=True, blank=True,
                                          on_delete=models.CASCADE, related_name='payment_plan')
    client         = models.OneToOneField('clients.Client', null=True, blank=True,
                                          on_delete=models.CASCADE, related_name='payment_plan')
    supplier_order = models.OneToOneField('logistics.SupplierOrder', null=True, blank=True,
                                          on_delete=models.CASCADE, related_name='payment_plan')
    deal           = models.OneToOneField('deals.Deal', null=True, blank=True,
                                          on_delete=models.CASCADE, related_name='payment_plan')
    steps          = models.JSONField(default=list)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_plans'

from django.db import models


class Payment(models.Model):
    invoice_ref  = models.CharField(max_length=200, db_index=True)
    deal         = models.ForeignKey(
        'deals.Deal', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='payments',
    )
    amount       = models.DecimalField(max_digits=18, decimal_places=2)
    currency     = models.CharField(max_length=10, default='USD')
    payment_date = models.DateField()
    method       = models.CharField(max_length=100, blank=True)
    notes        = models.TextField(blank=True)
    # payment: money received. refund: money returned to the client (negative).
    # credit_out / credit_in: client credit moved from one invoice to another (negative / positive),
    # linked by transfer_group so both sides are undone together.
    kind           = models.CharField(max_length=12, default='payment',
                                      choices=[('payment', 'Payment'), ('refund', 'Refund'),
                                               ('credit_out', 'Credit moved out'), ('credit_in', 'Client credit applied')])
    transfer_group = models.CharField(max_length=40, blank=True, db_index=True)
    recorded_by  = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f'{self.invoice_ref} — {self.amount} {self.currency}'

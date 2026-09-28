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
    recorded_by  = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f'{self.invoice_ref} — {self.amount} {self.currency}'

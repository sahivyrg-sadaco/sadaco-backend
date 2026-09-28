from django.db import models


class Supplier(models.Model):
    company_name  = models.CharField(max_length=300)
    contact_name  = models.CharField(max_length=200, blank=True)
    email         = models.EmailField(blank=True)
    phone         = models.CharField(max_length=50, blank=True)
    address_line1 = models.TextField(blank=True)
    address_line2 = models.TextField(blank=True)
    country       = models.CharField(max_length=100, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)
    incoterm      = models.CharField(max_length=20, blank=True)
    notes         = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'suppliers'
        ordering = ['company_name']

    def __str__(self):
        return self.company_name

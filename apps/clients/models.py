from django.db import models


class Client(models.Model):
    dropdown_name   = models.CharField(max_length=100, unique=True)
    full_name       = models.CharField(max_length=300)
    code            = models.IntegerField(unique=True)
    address_line1   = models.TextField(blank=True)
    address_line2   = models.TextField(blank=True)
    country         = models.CharField(max_length=100, blank=True)
    contact_name    = models.CharField(max_length=200, blank=True)
    contact_email   = models.EmailField(blank=True)
    contact_phone   = models.CharField(max_length=50,  blank=True)
    payment_terms   = models.CharField(max_length=100, default='Net 30')
    currency        = models.CharField(max_length=10,  default='USD')
    notes           = models.TextField(blank=True)
    drive_folder_id = models.CharField(max_length=200, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'clients'
        ordering = ['full_name']

    def __str__(self):
        return f'{self.dropdown_name} ({self.code})'

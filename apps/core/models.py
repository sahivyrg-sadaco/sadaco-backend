"""Options people add to dropdown lists, on top of the defaults in settings.py."""
from django.db import models


class ConfigOption(models.Model):
    KIND_CHOICES = [
        ('units',         'Unit'),
        ('payment_terms', 'Payment terms'),
        ('locations',     'Delivery point'),
    ]
    # Longest value each list's target field can hold.
    MAX_LENGTH = {'units': 50, 'payment_terms': 100, 'locations': 200}

    kind       = models.CharField(max_length=30, choices=KIND_CHOICES)
    value      = models.CharField(max_length=200)
    created_by = models.ForeignKey('accounts.User', null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'config_options'
        ordering = ['kind', 'value']
        unique_together = [('kind', 'value')]

    def __str__(self):
        return f'{self.kind}: {self.value}'


class CompanyEntity(models.Model):
    """
    Details for one selling entity (address, tax id, bank accounts per currency),
    edited by admins in the app. Overrides the defaults in settings.SELLER_ENTITIES.
    """
    name       = models.CharField(max_length=200, unique=True)
    details    = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_entities'

    def __str__(self):
        return self.name

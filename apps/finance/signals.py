"""A deal cost's recorded invoice becomes a payable automatically."""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from apps.costs.models import DealCost
from .services import sync_cost_payable


@receiver(post_save, sender=DealCost)
def cost_saved(sender, instance, **kwargs):
    sync_cost_payable(instance)


@receiver(pre_delete, sender=DealCost)
def cost_deleted(sender, instance, **kwargs):
    instance.actual_amount = None
    sync_cost_payable(instance)

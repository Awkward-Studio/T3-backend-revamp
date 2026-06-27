from django.db.models.signals import post_save
from django.dispatch import receiver
from vehicle_management.models import Car

from .services import ensure_wallet_for_car


@receiver(post_save, sender=Car)
def create_customer_wallet_for_car(sender, instance, created, **kwargs):
    if not created:
        return
    ensure_wallet_for_car(instance)

from .models import Restriction
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Restriction)
def post_save_restriction(sender, **kwargs):
    msg = "worked"
    pass

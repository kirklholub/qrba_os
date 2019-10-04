# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import IPzone


class Command(BaseCommand):
    help = "sets hostnames for ipzone"

    def handle(self, *args, **options):
        zones = IPzone.objects.get_queryset()
        print("zones: " + str(zones))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for z in zones:
            print("calling " + str(z) + ".set_hostnames() at " + str(now))
            z.set_hostnames()

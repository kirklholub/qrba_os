#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC


class Command(BaseCommand):
    help = "attempts to fetch domain controller ipzone info"

    def handle(self, *args, **options):
        dcs = WinDC.objects.get_queryset()
        print("domain controllers: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for dc in dcs:
            print("calling get_ipzone( " + str(dc) + ") at " + str(now))
            zones = dc.get_ipzone()
            print("get_ipzone( " + str(dc) + ") at " + str(now) + " returned " + str(zones))

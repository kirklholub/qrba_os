#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import DNSdomain


class Command(BaseCommand):
    help = "checks for authoritative WinDCs for a dns domain"

    def handle(self, *args, **options):
        domains = DNSdomain.objects.get_queryset()
        now = timezone.now() + datetime.timedelta(days=30)
        for d in domains:
            d.check_dcs()
            dcs = d.get_windcs()
            print(str(now) + " -- DCS: " + str(dcs))

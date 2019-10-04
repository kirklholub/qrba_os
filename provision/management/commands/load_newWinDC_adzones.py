#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC, IPzone


class Command(BaseCommand):
    help = "checks domain controller ipzone info"

    def handle(self, *args, **options):
        dcs = WinDC.objects.get_queryset()
        # print("domain controlers: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        # print("now: " + str(now))
        for dc in dcs:
            # print("calling " + str(dc) + ".load_neworgs() at " + str(now))
            state = dc.load_newipzones()
            print(str(dc) + ".load_newipzones() at " + str(now) + " returned state " + str(state))

            ipzones = dc.get_ipzone()
            print("ipzone are: " + str(ipzones))

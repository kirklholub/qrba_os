#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Restriction


class Command(BaseCommand):
    help = "returns ipzone from a Restriction"

    def handle(self, *args, **options):
        res = Restriction.objects.get_queryset()
        # print("domain controlers: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        # print("now: " + str(now))
        for r in res:
            # print("calling " + str(dc) + ".load_neworgs() at " + str(now))
            ipz = r.get_ipzone()
            print(str(r) + ".get_ipzone() at " + str(now) + " found " + str(ipz))
            print("len(ipz) = " + str(len(ipz)))
            zones = []
            for a in ipz:
                print("  a = " + str(a))
                zones.append(a)
            print("len(zones) = " + str(len(zones)))

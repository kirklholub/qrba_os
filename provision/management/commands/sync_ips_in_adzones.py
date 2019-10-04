#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC, IPzone


class Command(BaseCommand):
    help = "synchronizes ip addresss for all ipzone "

    def handle(self, *args, **options):
        dcs = WinDC.objects.get_queryset()
        # print("domain controlers: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        # print("now: " + str(now))
        for dc in dcs:
            print("calling " + str(dc) + ".load_neworgs() at " + str(now))
            activity = dc.sync_ips_in_all_WinDCs()
            print(str(dc) + ".sync_ips_in_all_WinDCs() at " + str(now) + " -- activity " + str(activity))

        allipzs = IPzone.objects.all()
        for ipz in allipzs:
            iplist = ipz.get_ipaddrs()
            print(str(ipz) + " has " + str(len(iplist)) + " hosts ")
            print("      iplist: " + str(iplist))

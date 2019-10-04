#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC, Cluster
from qrba import settings


class Command(BaseCommand):
    help = "checks domain controller organization info"

    def handle(self, *args, **options):
        dcs = WinDC.objects.get_queryset()
        print("domain controllers: " + str(dcs))
        clusters = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        cluster = clusters[0]
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for dc in dcs:
            print("calling " + str(dc) + ".load_neworgs() at " + str(now))
            state = dc.load_neworgs(cluster)
            print(str(dc) + ".load_neworgs() at " + str(now) + " returned state " + str(state))

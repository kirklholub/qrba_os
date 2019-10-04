#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from qrba import settings
from provision.models import Host, ActivityStat, ActivityType


class Command(BaseCommand):
    help = "updates all of the ActivityRunningStat objects"

    def handle(self, *args, **options):
        qr = ActivityStat.objects.all()
        if qr.count() == 0:
            firstacttype = ActivityType.objects.first()
            nhost = Host.objects.filter(name=settings.NONE_NAME)
            if nhost.count() != 1:
                print("could not find Host NONE")
                sys.exit(-1)
            nhost = nhost[0]
            actstat = ActivityStat(activitytype=firstacttype, host=nhost)
            actstat.save()
        else:
            actstat = qr[0]

        actstat.update_all_running_activity_stats()

#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError
import sys
import datetime
from django.utils import timezone
from provision.models import Activity, ActivityFetch, ActivityStat, ActivityRunningStat, ActivityType


class Command(BaseCommand):
    help = "Clears the system be removing all 'provision' ActivityStat and ActivityRunningStat objects -- all other qrba objects are not touched"

    def handle(self, *args, **options):
        qr = ActivityRunningStat.objects.all()
        qr.delete()

        qr = ActivityStat.objects.all()
        qr.delete()

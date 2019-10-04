#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import CLUSTER_TIME_SERIES_CHOICES, ClusterTimeSeriesType


class Command(BaseCommand):
    help = "initializes all ClusterTimeSeriesTypes"

    def handle(self, *args, **options):
        for key, val in CLUSTER_TIME_SERIES_CHOICES:
            qs = ClusterTimeSeriesType.objects.filter(activitytype=val, id=key)
            if qs.count() == 0:
                ctst = ClusterTimeSeriesType(activitytype=val)
                ctst.save()

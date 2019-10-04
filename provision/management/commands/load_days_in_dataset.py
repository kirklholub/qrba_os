#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import DAYS_IN_DATASET, DaysInDataset


class Command(BaseCommand):
    help = "initializes all DaysInDataset"

    def handle(self, *args, **options):
        for key, val in DAYS_IN_DATASET:
            qs = DaysInDataset.objects.filter(label=val, days=key)
            if qs.count() == 0:
                dds = DaysInDataset(label=val, days=key)
                dds.save()

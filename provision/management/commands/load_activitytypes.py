#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import ActivityType, ACTIVITY_CHOICES


class Command(BaseCommand):
    help = "initializes all ActivityTypes"

    def handle(self, *args, **options):
        for key, val in ACTIVITY_CHOICES:
            qs = ActivityType.objects.filter(activitytype=val, id=key)
            if qs.count() == 0:
                at = ActivityType(activitytype=val)
                at.save()

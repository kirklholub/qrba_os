#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError
import sys
import datetime
from django.utils import timezone
from provision.models import NfsExport


class Command(BaseCommand):
    help = "sets the updater field of all NfsExport and calls save()"

    def handle(self, *args, **options):
        exports = NfsExport.objects.all()
        for x in exports:
            print(str(x))
            x.updater = 'kirk'
            x.save()

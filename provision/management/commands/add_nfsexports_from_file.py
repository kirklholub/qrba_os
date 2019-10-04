#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Cluster


class Command(BaseCommand):
    help = "reads a formatted text file and creates NfsExport objects along with their requried objects"

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str)

    def handle(self, *args, **options):
        servers = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        print("servers: " + str(servers))
        now = timezone.now()
        print("now: " + str(now))
        filename = options['filename']
        for s in servers:
            msg = " calling " + str(s) + ".add_nfsexports_from_file( " + str(filename) + " )"
            print(msg)
            activity = s.add_nfsexports_from_file(filename)
            print("activity: " + str(activity))

#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Cluster
from qrba import settings


class Command(BaseCommand):
    help = "synchronizes cluster path related objects from the qumulo server to the system"

    def handle(self, *args, **options):
        servers = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        print("servers: " + str(servers))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for s in servers:
            print("server is: " + str(s))
            print("calling " + str(s) + ".sync_clusterpaths_from_cluster( " + str(s) + " ) at " + str(now))
            activity = s.sync_clusterpaths_from_cluster(s)
            print("   activity is " + str(activity) + " at " + str(now))

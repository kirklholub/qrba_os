#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Cluster


class Command(BaseCommand):
    help = "attempts to fetch cluster config info"

    def handle(self, *args, **options):
        servers = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        print("servers: " + str(servers))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for s in servers:
            print("server is: " + str(s))
            print("calling get_credentials( " + str(s) + ") at " + str(now))
            creds = s.get_credentials()
            print("   creds: = " + str(creds) + ") at " + str(now))

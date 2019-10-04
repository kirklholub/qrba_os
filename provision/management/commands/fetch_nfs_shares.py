#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Cluster


class Command(BaseCommand):
    help = "fetches all cluster nfs share information"

    def handle(self, *args, **options):
        servers = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        print("servers: " + str(servers))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for s in servers:
            print("server is: " + str(s))
            print("calling " + str(s) + ".fetch_nfs_shares( " + str(s) + ") at " + str(now))
            shares = s.fetch_nfs_shares(s)
            print("   shares: = " + str(shares) + ") at " + str(now))
            print("   lenshares: = " + str(len(shares)) + " at " + str(now))

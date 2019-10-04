#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import sys
import datetime
from django.utils import timezone
from provision.models import Cluster
from qrba import settings


class Command(BaseCommand):
    help = "synchronizes nfs exports from cluster prod to testcluster"

    def handle(self, *args, **options):
        qr = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        if qr.count() == 0:
            testserver = Cluster.objects.create(name=settings.QUMULO_devcluster['name'],
                                                ipaddr=settings.QUMULO_devcluster['ipaddr'],
                                                adminpassword=settings.QUMULO_devcluster['adminpassword'],
                                                port=settings.QUMULO_devcluster['port'])
            testserver.save()
        else:
            testserver = qr[0]

        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        print("testserver is: " + str(testserver))

        print("calling " + str(testserver) + ".sync_nfs_exports_from_cluster( " + str(testserver) + " ) at " + str(now))
        activity = testserver.sync_nfs_exports_from_cluster(testserver)
        print("   activity is " + str(activity) + " at " + str(now))


#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Cluster
from qrba import settings

class Command(BaseCommand):
    help = "synchronizes cluster path related objects from the testcluster to the integration cluster"

    def handle(self, *args, **options):
        qr = Cluster.objects.filter(name=settings.QUMULO_intcluster['name'])
        if qr.count() == 0:
            intserver = Cluster.objects.create(name=settings.QUMULO_intcluster['name'],
                                               ipaddr=settings.QUMULO_intcluster['ipaddr'],
                                               adminpassword=settings.QUMULO_intcluster['adminpassword'])
            intserver.save()
        else:
            intserver = qr[0]

        qr = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        if qr.count() == 0:
            testserver = Cluster.objects.create(name=settings.QUMULO_devcluster['name'],
                                                ipaddr=settings.QUMULO_devcluster['ipaddr'],
                                                adminpassword=settings.QUMULO_devcluster['adminpassword'])
            testserver.save()
        else:
            testserver = qr[0]

        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        print("intserver is: " + str(intserver))
        print("testserver is: " + str(testserver))

        print("calling " + str(intserver) + ".sync_clusterpaths_from_cluster( " + str(testserver) + " ) at " + str(now))
        activity = intserver.sync_clusterpaths_from_cluster(testserver)
        print("   activity is " + str(activity) + " at " + str(now))


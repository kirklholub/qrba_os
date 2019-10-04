#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Cluster
from qrba import settings


class Command(BaseCommand):
    help = "synchronizes cluster path related objects from the production cluster to itself"

    def handle(self, *args, **options):

        qr = Cluster.objects.filter(name=settings.QUMULO_prodcluster['name'])
        if qr.count() == 0:
            prodserver = Cluster.objects.create(name=settings.QUMULO_prodcluster['name'],
                                                ipaddr=settings.QUMULO_prodcluster['ipaddr'],
                                                adminpassword=settings.QUMULO_prodcluster['adminpassword'],
                                                port=settings.QUMULO_prodcluster['port'])
            prodserver.save()
        else:
            prodserver = qr[0]

        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        print("prodserver is: " + str(prodserver))
        print("calling " + str(prodserver) + ".sync_clusterpaths_from_cluster( " + str(prodserver) + ") at " + str(now))
        activity = prodserver.sync_clusterpaths_from_cluster(prodserver)
        print("   activity is " + str(activity) + " at " + str(now))

        # print("calling " + str(prodserver) + ".sync_clusterpaths_to_cluster( " + str(prodserver) + ") at " + str(now))
        # activity = prodserver.sync_clusterpaths_to_cluster(prodserver)
        # print("   activity is " + str(activity) + " at " + str(now))

        print("calling " + str(prodserver) + ".check_all_quotas() at " + str(now))
        prodserver.check_all_quotas()

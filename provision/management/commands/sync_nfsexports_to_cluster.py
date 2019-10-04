#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import sys
import datetime
from django.utils import timezone
from provision.models import Cluster


class Command(BaseCommand):
    help = "synchronizes nfsexports from the system to the cluster"

    def handle(self, *args, **options):
        now = timezone.now() + datetime.timedelta(days=30)

        cluster = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        if cluster.count() == 1:
            cluster = cluster[0]
            print("cluster is " + str(cluster.name))
            if cluster.alive() is False:
                print("  could not connect to cluster " + str(cluster) + " at " + str(now) + "  exiting now!! ")
                sys.exit(-1)

            print("now: " + str(now))
            print("calling " + str(cluster.name) + ".sync_nfs_exports_to_cluster ( " + str(
                cluster.name) + ") at " + str(now))
            activity = cluster.sync_nfs_exports_to_cluster(cluster)
            print("   activity is " + str(activity) + " at " + str(now))
        else:
            print("found " + str(cluster.count()) + " clusters -- expecting 1")

#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC, IPzone, Cluster
from qrba import settings

class Command(BaseCommand):
    help = "call managment script to keep system in-sync with DC controllers and clusters"

    def handle(self, *args, **options):
        now = timezone.now() + datetime.timedelta(days=30)
        print("starting check_qrba now: " + str(now))

        dcs = WinDC.objects.get_queryset()
        print("  domain controllers: " + str(dcs))

        clusters = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        cluster = clusters[0]
        for dc in dcs:
            # print("    calling " + str(dc) + ".load_neworgs() at " + str(now))
            state = dc.load_neworgs(cluster)
            print("      " + str(dc) + ".load_neworgs() returned state " + str(state))

            # print("    calling " + str(dc) + ".load_neworgs() at " + str(now))
            state = dc.load_newipzones()
            print("      " + str(dc) + ".load_newipzones() returned state " + str(state))

            # print("    calling " + str(dc) + ".load_neworgs() at " + str(now))
            state = dc.load_newhosts()
            print("      " + str(dc) + ".load_newhosts() returned state " + str(state))

        clusters = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        print("\n" + "clusters: " + str(clusters))
        for c in clusters:
            # print("  cluster is: " + str(c))
            # print("    calling sync_clusterpaths_from_cluster( " + str(c) + ") at " + str(now))
            activity = c.sync_clusterpaths_from_cluster(c)
            print("      sync_clusterpaths_from_cluster returned activity: " + str(activity))
            print("    NOT calling sync_nfs_exports_from_cluster( " + str(c) + ") at " + str(now))
            # activity = c.sync_nfs_exports_from_cluster()
            # print("      sync_nfs_exports_from_cluster returned activity: " + str(activity) )

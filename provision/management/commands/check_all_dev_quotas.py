#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC, IPzone, Cluster
from qrba import settings


class Command(BaseCommand):
    help = "checks status of all quotas on the dev cluster"

    def handle(self, *args, **options):
        now = timezone.now() + datetime.timedelta(days=30)
        print("starting check_qrba now: " + str(now))

        clusters = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        cluster = clusters[0]
        print("cluster is " + str(cluster))
        cluster.check_all_quotas()

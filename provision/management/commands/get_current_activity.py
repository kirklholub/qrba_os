#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from qrba import settings
from provision.models import Cluster


class Command(BaseCommand):
    help = "stores the current throughput in IOP info"

    def handle(self, *args, **options):
        qr = Cluster.objects.filter(name=settings.QUMULO_prodcluster['name'])
        if qr.count() == 0:
            cluster = Cluster(name=settings.QUMULO_prodcluster['name'], ipaddr=settings.QUMULO_prodcluster['ipaddr'],
                              adminpassword=settings.QUMULO_prodcluster['adminpassword'], port=8000)
            cluster.save()
        else:
            cluster = qr[0]

        cluster.get_current_activity()

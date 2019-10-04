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
    help = "stores the current cluster slot status info"

    def handle(self, *args, **options):
        qr = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        if qr.count() == 0:
            cluster = Cluster(name=settings.QUMULO_devcluster['name'], ipaddr=settings.QUMULO_devcluster['ipaddr'],
                              adminpassword=settings.QUMULO_devcluster['adminpassword'], port=8000)
            cluster.save()
        else:
            cluster = qr[0]

        cluster.get_slot_status()

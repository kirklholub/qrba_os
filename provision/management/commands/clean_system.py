#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError
import sys
import datetime
from django.utils import timezone
from provision.models import IPzone, Clusterpath, Cluster, DNSdomain, Host, NfsExport, Organization, Quota, QuotaUsage, \
    Report, \
    Restriction, Sysadmin, WinDC, QuotaEvent


class Command(BaseCommand):
    help = "Clears the system be removing all 'provision' objects -- admin objects are not touched"

    def handle(self, *args, **options):

        nfxs = NfsExport.objects.all()
        for x in nfxs:
            x.do_not_delete = False
            x.delete()

        rs = Restriction.objects.all()
        for r in rs:
            r.do_not_delete = False
            r.delete()

        cps = Clusterpath.objects.all()
        for cp in cps:
            cp.do_not_delete = False
            cp.delete()

        zones = IPzone.objects.all()
        for z in zones:
            z.immutable = False
            z.delete()

        qr = Cluster.objects.all()
        qr.delete()
        qr = DNSdomain.objects.all()
        qr.delete()

        qr = Host.objects.all()
        qr.delete()

        qr = Organization.objects.all()
        qr.delete()
        # qr = QuotaUsage.history.all()
        # qr.delete()
        qs = Quota.objects.all()
        for q in qs:
            q.do_not_delete = False
            q.delete()

        qr = QuotaUsage.objects.all()
        qr.delete()

        qr = QuotaEvent.objects.all()
        qr.delete()

        qr = Report.objects.all()
        qr.delete()


        qr = Sysadmin.objects.all()
        qr.delete()
        qr = WinDC.objects.all()
        qr.delete()
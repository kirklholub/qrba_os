#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC


class Command(BaseCommand):
    help = "attempts to fetch domain controller host info"

    def handle(self, *args, **options):
        dcs = WinDC.objects.get_queryset().filter(name='centrifyX.privatedomain.org.tld')
        print("domain controlers: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for dc in dcs:
            print("calling get_hosts( " + str(dc) + ") at " + str(now))
            hostlist = dc.get_hosts()
            print("get_hosts( " + str(dc) + ") at " + str(now))

            print("hosts: " + str(hostlist) + "\n\n")

#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import WinDC, IPzone


class Command(BaseCommand):
    help = "checks domain controller host info"

    def handle(self, *args, **options):
        dcs = WinDC.objects.get_queryset().filter(name='centrifyX.private.org.tld')
        # print("domain controlers: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        # print("now: " + str(now))
        for dc in dcs:
            # print("calling " + str(dc) + ".load_neworgs() at " + str(now))
            state = dc.load_newhosts()
            print(str(dc) + ".load_newhosts() at " + str(now) + " returned state " + str(state))

            hosts = dc.get_hosts()
            print("hosts are: " + str(hosts))

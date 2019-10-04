#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Host


class Command(BaseCommand):
    help = "checks the hostnames"

    def handle(self, *args, **options):
        hosts = Host.objects.get_queryset()
        # print("hosts: " + str(hosts))
        now = timezone.now()
        # print("now: " + str(now))
        for h in hosts:
            # print("calling check_hostip( " + str(h) + ") at " + str(now))
            when = h.check_hostname()
            # print("check_hostip( " + str(h) + ") updated at " + str(when))

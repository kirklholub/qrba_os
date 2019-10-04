#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Organization


class Command(BaseCommand):
    help = "checks the hosts"

    def handle(self, *args, **options):
        organizations = Organization.objects.get_queryset()
        print("organizations: " + str(organizations))
        now = timezone.now() + datetime.timedelta(days=30)
        print("now: " + str(now))
        for org in organizations:
            print("calling " + str(org) + ".check_hosts() at " + str(now))
            state = org.check_hosts()
            print(str(org) + ".check_hosts() returned " + str(state))

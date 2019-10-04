#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Organization


class Command(BaseCommand):
    help = "popluates hosts for all Organizations"

    def handle(self, *args, **options):
        orgs = Organization.objects.get_queryset()
        print("orgs: " + str(orgs))
        nohosts = []
        for o in orgs:
            # print("calling " + str(o) + ".check_hosts() at " + str(now))
            activity = o.check_hosts()

            if int(activity['lendchosts']) == int(0):
                nohosts.append(o)
            else:
                print("    activity: " + str(activity))

        print("no dchosts for: " + str(nohosts))

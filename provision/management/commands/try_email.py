#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

sys.path.append("/Users/holub/PycharmProjects/qrba")
os.environ["DJANGO_SETTINGS_MODULE"] = "qrba.settings"
# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

from provision.models import Quota


class Command(BaseCommand):
    help = "test sending email"

    def handle(self, *args, **options):
        qs = Quota.objects.get_queryset()
        qs.first()
        if qs.count() > 0:
            q = qs[0]
            msg = q.test_email()
            print("msg = " + str(msg))

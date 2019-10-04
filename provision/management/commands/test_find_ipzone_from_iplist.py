# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import IPzone


class Command(BaseCommand):

    def handle(self, *args, **options):
        # iplist = options['iplist']

        iplist = []
        iplist.append('137.75.238.75')
        ipz = IPzone.objects.all()
        if ipz.count() > 0:
            ipz = ipz[0]
            ipz.find_ipzone_from_iplist(iplist)

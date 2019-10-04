# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Organization


class Command(BaseCommand):
    help = "checks the ipzone"

    def handle(self, *args, **options):
        organizations = Organization.objects.get_queryset()
        print("organizations: " + str(organizations))
        now = timezone.now() + datetime.timedelta(days=30)
        #print("now: " + str(now))
        for org in organizations:
            print("calling " + str(org) + ".check_ipzones() at " + str(now))
            state = org.check_ipzones()
            print(str(org) + ".check_ipzones() returned " + str(state))

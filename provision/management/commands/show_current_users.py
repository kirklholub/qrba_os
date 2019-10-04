#!/usr/bin/python
from __future__ import unicode_literals

import os, sys

# https://www.codingforentrepreneurs.com/blog/django-tutorial-get-list-of-current-users/
from django.core.management.base import BaseCommand, CommandError

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone


class Command(BaseCommand):
    help = "show list of current users"

    def handle(self, *args, **options):
        all_sessions = Session.objects.all()

        active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
        for session in active_sessions:
            print("pk: " + str(session.pk) + " expires " + str(session.expire_date))

        user_id_list = []
        for session in active_sessions:
            data = session.get_decoded()
            user_id_list.append(data.get('_auth_user_id', None))
            print("pk: " + str(session.pk) + " expires " + str(session.expire_date))


        current_users = User.objects.filter(id__in=user_id_list)
        print("\ncurrent users:")
        for u in current_users:
            name = u.get_full_name()
            if u.is_authenticated:
                print("   " + str(name) + " is authenticated")

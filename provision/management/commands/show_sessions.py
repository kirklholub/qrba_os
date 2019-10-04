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
        active_sessions = Session.objects.filter(expire_date__gte=timezone.now())

        user_id_list = []
        for session in active_sessions:
            data = session.get_decoded()
            user_id_list.append(data.get('_auth_user_id', None))
            # Query all logged in users based on id list

        current_users = User.objects.filter(id__in=user_id_list)
        print("current users:")
        for u in current_users:
            if u.is_authenticated:
                print("   " + str(u) + " is authenticated")
            else:
                print("   " + str(u) + " is a user")

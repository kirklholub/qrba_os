#!/usr/bin/python
from __future__ import unicode_literals

import os
import sys
import datetime

sys.path.append("/Users/holub/PycharmProjects/qrba")
os.environ["DJANGO_SETTINGS_MODULE"] = "qrba.settings"
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, Permission

import fileinput
from provision.models import Organization, Sysadmin
import logging

logger = logging.getLogger('qrba.models')

from qrba import settings

User = get_user_model()

class Command(BaseCommand):
    help = "reads a formatted text file and creates user objects"

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str)

    def handle(self, *args, **options):

        creator_msg = "add_users_from_file"

        # Insure the placeholder Organization exits
        now = datetime.datetime.utcnow()
        orgs = Organization.objects.filter(name=settings.NONE_NAME)
        if orgs.count() < 1:
            norg = Organization(name=settings.NONE_NAME)
            norg.save()
            now = datetime.datetime.utcnow()
            msg = str(now) + ":Organization:" + str(settings.NONE_NAME) + ":" + creator_msg
            logger.info(msg)
        else:
            norg = orgs[0]

        all_permissions = Permission.objects.all()
        addipz = all_permissions.filter(codename='add_ipzone')
        chgipz = all_permissions.filter(codename='change_ipzone')
        delipz = all_permissions.filter(codename='delete_ipzone')
        addnfs = all_permissions.filter(codename='add_nfsexport')
        chgnfs = all_permissions.filter(codename='change_nfsexport')
        delnfs = all_permissions.filter(codename='delete_nfsexport')
        addquota = all_permissions.filter(codename='add_quota')
        chgquota = all_permissions.filter(codename='change_quota')
        delquota = all_permissions.filter(codename='delete_quota')
        addreport = all_permissions.filter(codename='add_report')
        chgreport = all_permissions.filter(codename='change_report')
        delreport = all_permissions.filter(codename='delete_report')
        addrestriction = all_permissions.filter(codename='add_restriction')
        chgrestriction = all_permissions.filter(codename='change_restriction')
        delrestriction = all_permissions.filter(codename='delete_restriction')
        addclusterpath = all_permissions.filter(codename='add_clusterpath')
        chgclusterpath = all_permissions.filter(codename='change_clusterpath')
        delclusterpath = all_permissions.filter(codename='delete_clusterpath')
        delquotausage = all_permissions.filter(codename='delete_quotausage')

        try:
            sysadmin = Group.objects.get(name='sysadmin')

        except:
            sysadmin = Group.objects.create(name='sysadmin')
            now = datetime.datetime.utcnow()
            msg = str(now) + ":Groupobjectscreate:sysadmin:" + creator_msg
            logger.info(msg)

        sysadmin.permissions.add(addipz[0])
        sysadmin.permissions.add(chgipz[0])
        sysadmin.permissions.add(delipz[0])
        sysadmin.permissions.add(addnfs[0])
        sysadmin.permissions.add(chgnfs[0])
        sysadmin.permissions.add(delnfs[0])
        sysadmin.permissions.add(addquota[0])
        sysadmin.permissions.add(chgquota[0])
        sysadmin.permissions.add(delquota[0])
        sysadmin.permissions.add(addreport[0])
        sysadmin.permissions.add(chgreport[0])
        sysadmin.permissions.add(delreport[0])
        sysadmin.permissions.add(addrestriction[0])
        sysadmin.permissions.add(chgrestriction[0])
        sysadmin.permissions.add(delrestriction[0])
        sysadmin.permissions.add(addclusterpath[0])
        sysadmin.permissions.add(chgclusterpath[0])
        sysadmin.permissions.add(delclusterpath[0])
        sysadmin.permissions.add(delquotausage[0])


        filename = options['filename']
        for line in fileinput.input(filename):
            if '#' in str(line):
                pass
            else:
                # print(str(line))
                (username, password, email, is_a_superuser, orglist) = line.split(':')
                is_a_superuser = str(is_a_superuser)
                if 'True' in is_a_superuser:
                    is_a_superuser = True

                orglist = str(orglist).encode('ascii', 'ignore')
                orglist = orglist.replace('\n', '').encode('ascii', 'ignore')
                orglist = orglist.replace(' ', '', 1000).encode('ascii', 'ignore')
                orglist = orglist.replace('[', '').encode('ascii', 'ignore')
                orglist = orglist.replace(']', '').encode('ascii', 'ignore')
                orglist = orglist.split(',')
                orgs = []
                for o in orglist:
                    orgs.append(str(o).lower())

                # all uses need NONE org
                orgs.append(norg)

                if password is not None:
                    username = str(username).strip()
                    password = str(password).strip()
                    email = str(email).strip()
                    firstname = str(email).split('@')
                    firstname = firstname[0]
                    firstname = firstname.split('.')
                    lastname = firstname[len(firstname) - 1]
                    firstname = firstname[0]

                    try:
                        user = User.objects.create_user(username=username, email=email, is_staff=True,
                                                        first_name=firstname, last_name=lastname)
                        user.set_password(password)
                        user.save()
                        sysadmin.user_set.add(user)
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":Userobjectscreateuser:" + str(user) + ":" + creator_msg
                        logger.info(msg)
                    except:
                        # User may already exist (created as a superuser earlier)
                        pass

                    try:
                        sa = Sysadmin.objects.filter(name=username)
                        if sa.count() < 1:
                            sa = Sysadmin(name=username, is_a_superuser=is_a_superuser)
                            sa.save()
                            now = datetime.datetime.utcnow()
                            msg = str(now) + ":Sysadmin:" + str(username) + ":" + creator_msg
                            logger.info(msg)
                        else:
                            sa = sa[0]

                        if is_a_superuser is True:
                            sa.is_a_superuser = True

                        for o in orgs:
                            qs = Organization.objects.filter(name=o)
                            if qs.count() < 1:
                                org = Organization(name=o)
                                org.save()
                                now = datetime.datetime.utcnow()
                                msg = str(now) + ":Organization:" + str(o) + ":" + creator_msg
                                logger.info(msg)
                            else:
                                org = qs[0]
                            sa.organizations.add(org)

                        qs = Organization.objects.filter(name=orgs[0])
                        if qs.count() < 1:
                            homeorg = Organization(name=orgs[0])
                            homeorg.save()
                            now = datetime.datetime.utcnow()
                            msg = str(now) + ":Organization:" + str(orgs[0]) + ":" + creator_msg
                            logger.info(msg)
                        else:
                            homeorg = qs[0]
                        sa.organization = homeorg
                        sa.save()
                        assert authenticate(username=username, password=password)
                    except:
                        print 'There was a problem creating the user: {0}.  Error: {1}.' \
                            .format(username, sys.exc_info()[1])


#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import sys
from provision.models import Host, WinDC, Organization


class Command(BaseCommand):
    help = "checks and if needed updates the organization field for ALL hosts"

    def handle(self, *args, **options):
        needupdate = []
        for h in Host.objects.all():
            if h.organization is None:
                needupdate.append(h)
        if len(needupdate) > 0:
            wdc = WinDC.objects.all()
            if wdc.count() > 0:
                wdc = wdc[0]
                hosts_by_org = wdc.get_hosts_by_org_from_ldap()
                for org in hosts_by_org.keys():
                    qr = Organization.objects.filter(name=org)
                    if qr.count() > 0:
                        organiziation = qr[0]
                    else:
                        print("could not find organization " + str(org))
                        sys.exit(-1)

                    hosts = str(hosts_by_org[org])
                    for h in needupdate:
                        if str(h) in hosts:
                            msg = "updating " + str(h)
                            print(msg)
                            iam = Host.objects.filter(name=h)
                            if iam.count() > 0:
                                iam = iam[0]
                                iam.organization = organiziation
                                iam.save()
                            else:
                                print("coud not find host " + str(h))
            else:
                msg = "no wdc found for Host " + str(self)
                print(msg)
                sys.exit(-1)

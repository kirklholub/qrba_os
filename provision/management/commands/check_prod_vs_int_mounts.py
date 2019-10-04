#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import sys
import commands
import datetime
from provision.models import Cluster
from qrba import settings


class Command(BaseCommand):
    help = "compares output of 'showmount -e' for int versus the prod cluster"

    def handle(self, *args, **options):
        now = datetime.datetime.utcnow()
        print("starting check_prod_vs_int_mounts now: " + str(now))

        intcluster = Cluster.objects.filter(name=settings.QUMULO_intcluster['name'])
        if intcluster.count() == 0:
            intcluster = Cluster(name=settings.QUMULO_intcluster['name'], ipaddr=settings.QUMULO_intcluster['ipaddr'],
                                 adminpassword=settings.QUMULO_intcluster['adminpassword'], port=8000)
            intcluster.save()
        else:
            intcluster = intcluster[0]

        prodcluster = Cluster.objects.filter(name=settings.QUMULO_prodcluster['name'])
        if prodcluster.count() == 0:
            prodcluster = Cluster(name=settings.QUMULO_prodcluster['name'],
                                  ipaddr=settings.QUMULO_prodcluster['ipaddr'],
                                  adminpassword=settings.QUMULO_prodcluster['adminpassword'], port=8000)
            prodcluster.save()
        else:
            prodcluster = prodcluster[0]

        intbymount = {}
        prodbymount = {}

        cmd = "/usr/bin/showmount -e " + str(intcluster.ipaddr)
        # print(cmd)
        result = commands.getstatusoutput(cmd)
        if result[0] == 0:
            results = result[1].split("\n")
            for line in results:
                if 'Exports list' in str(line):
                    continue
                thisline = line.split()
                tmp = set()
                for i in range(1, len(thisline)):
                    tmp.add(thisline[i])
                intbymount[thisline[0]] = tmp
        else:
            print("error fetching data for cluster " + str(intcluster))

        intmounts = intbymount.keys()
        # for m in intmounts:
        #    print(str(m) + ": " + str(intbymount[m]))

        cmd = "/usr/bin/showmount -e " + str(prodcluster.ipaddr)
        # print(cmd)
        result = commands.getstatusoutput(cmd)
        if result[0] == 0:
            results = result[1].split("\n")
            for line in results:
                if 'Exports list' in str(line):
                    continue
                thisline = line.split()
                tmp = set()
                for i in range(1, len(thisline)):
                    tmp.add(thisline[i])
                prodbymount[thisline[0]] = tmp
        else:
            print("error fetching data for cluster " + str(prodcluster))

        prodmounts = prodbymount.keys()
        # for m in prodmounts:
        #    print(str(m) + ": " + str(prodbymount[m]))

        intmounts.sort()
        prodmounts.sort()
        if intmounts != prodmounts:
            print("intmounts not equal prodmounts!")
            sys.exit(-1)

        nummounts = len(prodmounts)
        print("found " + str(nummounts)) + " mountpoints"
        i = 1
        for m in prodmounts:
            prodset = prodbymount[m]
            intset = intbymount[m]
            difference = prodset.difference(intset)
            if len(difference) > 0:
                print(str(i) + " -- found difference for " + str(m))
                print("         prodset: " + str(prodset))
                print("         intset: " + str(intset))
            else:
                print(str(i) + " -- " + str(m) + " is OK")
            i = i + int(1)

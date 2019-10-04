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
    help = "compares output of 'showmount -e' for integration vs dev cluster"

    def handle(self, *args, **options):
        now = datetime.datetime.utcnow()
        print("starting check_int_vs_dev_mounts now: " + str(now))

        devcluster = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        intcluster = Cluster.objects.filter(name=settings.QUMULO_intcluster['name'])

        devbymount = {}
        intbymount = {}

        cmd = "/usr/bin/showmount -e " + str(devcluster[0].ipaddr)
        # print(cmd)
        result = commands.getstatusoutput(cmd)
        if result[0] == 0:
            results = result[1].split("\n")
            for line in results:
                if line[0:7] == 'Exports':
                    continue
                thisline = line.split()
                tmp = set()
                for i in range(1, len(thisline)):
                    tmp.add(thisline[i])
                devbymount[thisline[0]] = tmp
        else:
            print("error fetching data for cluster " + str(devcluster))

        # print( "\n\ndev_mounts:\n")

        devmounts = devbymount.keys()
        # for m in devmounts:
        #    print(str(m) + ": " + str(devbymount[m]))

        cmd = "/usr/bin/showmount -e " + str(intcluster[0].ipaddr)
        # print(cmd)
        result = commands.getstatusoutput(cmd)
        if result[0] == 0:
            results = result[1].split("\n")
            for line in results:
                if line[0:7] == 'Exports':
                    continue
                thisline = line.split()
                tmp = set()
                for i in range(1, len(thisline)):
                    tmp.add(thisline[i])
                intbymount[thisline[0]] = tmp
        else:
            print("error fetching data for cluster " + str(intcluster))

        # print( "\n\nint_mounts:\n")
        intmounts = intbymount.keys()
        # for m in intmounts:
        #    print(str(m) + ": " + str(intbymount[m]))

        devmounts.sort()
        intmounts.sort()

        # print( "found " + str(len(devmounts))) + " devmounts and " + str(len(intmounts)) + " intmounts"
        if devmounts != intmounts:
            print("devmounts not equal intmounts!")
            # sys.exit(-1)

        okcount = 0
        # print( "differences:")
        for m in intmounts:
            intlist = []
            for ip in intbymount[m]:
                intlist.append(str(ip).strip().encode('ascii', 'ignore'))

            devlist = []
            try:
                if devbymount[m]:
                    for ip in devbymount[m]:
                        devlist.append(str(ip).strip().encode('ascii', 'ignore'))
            except:
                print("    devbymount[ " + str(m) + " ] not found")
                okcount = okcount - 1

            difference = set(devlist).difference(intlist)
            # print( "     " + str(m) + ": " + str(difference))
            if len(difference) > 0:
                # print("found difference >" + str(difference) + "< for " + str(m))
                # print("      len(difference) = " + str(len(difference)))
                withmarker = 0
                for ip in difference:
                    if settings.IPZONE_MARKER_BASE in str(ip):
                        withmarker = withmarker + 1
                if withmarker == len(difference):
                    okcount = okcount + 1
                # print("      intlist: " + str(intlist))
                # print("      devlist: " + str(devlist))
            else:
                if difference != set([]):
                    print("    mount " + str(m) + " is OK")
                    okcount = okcount + 1
                else:
                    print("    mount " + str(m) + " does not exist in dev")

        if okcount == len(intmounts):
            print(str(okcount) + " mounts OK -- int vs dev")
        else:
            print("problem with one or more mounts int vs dev\n")

        okcount = 0
        # print( "differences:")
        for m in devmounts:
            devlist = []
            for ip in devbymount[m]:
                devlist.append(str(ip).strip().encode('ascii', 'ignore'))

            intlist = []
            try:
                if intbymount[m]:
                    for ip in intbymount[m]:
                        intlist.append(str(ip).strip().encode('ascii', 'ignore'))
            except:
                print("    intbymount[ " + str(m) + " ] not found")
                okcount = okcount - 1

            difference = set(intlist).difference(devlist)
            # print( "     " + str(m) + ": " + str(difference))
            if len(difference) > 0:
                # print("found difference >" + str(difference) + "< for " + str(m))
                # print("      len(difference) = " + str(len(difference)))
                withmarker = 0
                for ip in difference:
                    if settings.IPZONE_MARKER_BASE in str(ip):
                        withmarker = withmarker + 1
                if withmarker == len(difference):
                    okcount = okcount + 1
                # print("      intlist: " + str(intlist))
                # print("      devlist: " + str(devlist))
            else:
                if difference == set([]):
                    # print("    mount " + str(m) + " is OK")
                    okcount = okcount + 1
                else:
                    print("    mount " + str(m) + " does not exist in int")

        if okcount == len(intmounts):
            print(str(okcount) + " mounts OK -- dev vs int")
        else:
            print("problem with one or more mounts -- dev vs int")
            print("    okcount = " + str(okcount) + " for devlen " + str(len(devmounts)) + " and intlen " + str(
                len(intmounts)))

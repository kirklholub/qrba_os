# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

from provision.models import IPzone, NfsExport, Restriction
import sys

class Command(BaseCommand):
    help = "ipdates an ipzmarks to repair duplicates injected by a bug in qrba"

    def add_arguments(self, parser):
        parser.add_argument('zonename', type=str)

    def handle(self, *args, **options):
        zonename = options['zonename']
        zone = IPzone.objects.filter(name=zonename)

        if zone.count() != 1:
            print( "cannot find ipzone " + str(zonename))
            sys.exit(-1)
        unset = set()
        niipa = set()

        ipzmarker = zone.get_ipzone_marker()
        if 'unset' in str(ipzmarker):
            print("ipzmarker unset for zone " + str(zone))
            # z.set_ipaddrs(ipzmarker)
            unset.add(str(zone))

        ipaddrs = zone.get_ipaddrs()
        if str(ipzmarker) not in str(ipaddrs):
            print("ipzmarker " + str(ipzmarker) + " not found in ipaddrs for z " + str(zone))
            niipa.add(str(zone))
            #ipaddrs.append(ipzmarker)
            #zone.set_ipaddrs(ipaddrs)

            #rpset = set()
            #for r in Restriction.objects.all():
            #    for ipz in r.get_ipzones():
            #        if ipz.__eq__(z):
            #            rpset.add(r)

            #nsfxparents = set()
            #for x in NfsExport.objects.all():
            #    xrqs = x.restrictions.get_queryset()
            #    for xr in xrqs:
            #        for r in rpset:
            #            if r.__eq__(xr):
            #                nsfxparents.add(x)

            #if len(nsfxparents) > 0:
            #    print("   nsfparents:")
            #    for x in nsfxparents:
            #        msg = "       " + str(x)
            #        print(msg)
            #    print("\n")

            # else:
            #    print( "ipzmarker " + str(ipzmarker) + " found for z " + str(z) )

            # ipzmarker = z.get_ipzone_marker()
            # ipaddrs = z.get_ipaddrs()
            # if str(ipzmarker) not in str(ipaddrs):
            #    print( "   unset ipzmarker for z " + str(z))

        unlist = []
        for x in unset:
            unlist.append(x)
        unlist.sort()
        nilist = []
        for x in niipa:
            nilist.append(x)
        nilist.sort()

        print("num unset: " + str(len(unlist)))
        print("num niipa: " + str(len(nilist)))
        print("unset: " + str(unset))
        print("niipa: " + str(niipa))

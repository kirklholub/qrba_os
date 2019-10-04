# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

from provision.models import IPzone, NfsExport, Restriction


class Command(BaseCommand):
    help = "checks the ipzmarkers in all ipzones"

    def handle(self, *args, **options):
        zones = IPzone.objects.all()
        numzones = len(zones)
        print("found " + str(numzones) + " zones")
        unset = set()
        niipa = set()
        for z in zones:
            if '#None' in str(z):
                continue
            ipzmarker = z.get_ipzone_marker()
            if 'unset' in str(ipzmarker):
                print("ipzmarker unset for z " + str(z))
                # z.set_ipaddrs(ipzmarker)
                unset.add(str(z))

            ipaddrs = z.get_ipaddrs()
            if str(ipzmarker) not in str(ipaddrs):
                print("ipzmarker " + str(ipzmarker) + " not found in ipaddrs for z " + str(z))
                niipa.add(str(z))
                ipaddrs.append(ipzmarker)
                z.set_ipaddrs(ipaddrs)

                rpset = set()
                for r in Restriction.objects.all():
                    for ipz in r.get_ipzones():
                        if ipz.__eq__(z):
                            rpset.add(r)

                nsfxparents = set()
                for x in NfsExport.objects.all():
                    xrqs = x.restrictions.get_queryset()
                    for xr in xrqs:
                        for r in rpset:
                            if r.__eq__(xr):
                                nsfxparents.add(x)

                if len(nsfxparents) > 0:
                    print("   nsfparents:")
                    for x in nsfxparents:
                        msg = "       " + str(x)
                        print(msg)
                    print("\n")
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

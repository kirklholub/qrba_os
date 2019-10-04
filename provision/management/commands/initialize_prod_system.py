#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError
import sys
import datetime
from django.utils import timezone
from provision.models import IPzone, Clusterpath, Cluster, DNSdomain, Host, NfsExport, Organization, Quota, QuotaUsage, \
    Report, \
    Restriction, Sysadmin, WinDC, ActivityType, ACTIVITY_CHOICES, DAYS_IN_DATASET, DaysInDataset, \
    CLUSTER_TIME_SERIES_CHOICES, ClusterTimeSeriesType
from qrba import settings
import qumulo.rest.version
import logging

logger = logging.getLogger('qrba.models')


def qlogin(host, user, passwd, port):
    '''Obtain credentials from the REST server'''
    conninfo = None
    creds = None

    try:
        # Create a connection to the REST server
        conninfo = qumulo.lib.request.Connection(host, int(port))

        # Provide username and password to retreive authentication tokens
        # used by the credentials object
        login_results, _ = qumulo.rest.auth.login(
            conninfo, None, user, passwd)

        # Create the credentials object which will be used for
        # authenticating rest calls
        creds = qumulo.lib.auth.Credentials.from_login_response(login_results)
    except Exception, excpt:
        print "Error connecting to the REST server: %s" % excpt
        # print __doc__
        # sys.exit(1)
    return (conninfo, creds)


class Command(BaseCommand):
    help = "Initializes the system by loading all domains, ipzone, and hosts into the production cluster"

    def handle(self, *args, **options):
        msg = "QRBA API version: " + str(settings.QUMULO_API_VERSION)
        print(msg)
        (conninfo, creds) = qlogin(settings.QUMULO_prodcluster['ipaddr'], 'admin',
                                   settings.QUMULO_prodcluster['adminpassword'], settings.QUMULO_prodcluster['port'])
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name)
            logger.critical(msg)
            sys.exit(-1)
        qr = qumulo.rest.version.version(conninfo, None)
        msg = "cluster API version: " + str(qr)

        qr = Cluster.objects.filter(name=settings.QUMULO_prodcluster['name'])
        if qr.count() == 0:
            cluster = Cluster(name=settings.QUMULO_prodcluster['name'], ipaddr=settings.QUMULO_prodcluster['ipaddr'],
                              adminpassword=settings.QUMULO_prodcluster['adminpassword'], port=8000)
            cluster.save()
        else:
            cluster = qr[0]

        # load all activitytype objects
        for key, val in ACTIVITY_CHOICES:
            qs = ActivityType.objects.filter(activitytype=val, id=key)
            if qs.count() == 0:
                at = ActivityType(activitytype=val)
                at.save()

        for key, val in DAYS_IN_DATASET:
            qs = DaysInDataset.objects.filter(label=val, days=key)
            if qs.count() == 0:
                dds = DaysInDataset(label=val, days=key)
                dds.save()

        for key, val in CLUSTER_TIME_SERIES_CHOICES:
            qs = ClusterTimeSeriesType.objects.filter(activitytype=val, id=key)
            if qs.count() == 0:
                ctst = ClusterTimeSeriesType(activitytype=val)
                ctst.save()

        # Insure the placeholder Organization, IPzone, Host, Quota, and Restriction exist (needed for 'individual_hosts' to work
        # Leading '#' is used to force these objects to top of the sort order
        qr = Host.objects.filter(name=settings.NONE_NAME)
        if qr.count() < 1:
            qr = Organization.objects.filter(name=settings.NONE_NAME)
            if qr.count() < 1:
                now = datetime.datetime.utcnow()
                norg = Organization(name=settings.NONE_NAME)
                norg.save()
                msg = str(now) + ":Organization:" + str(settings.NONE_NAME) + ":initialize_system"
                logger.info(msg)
            else:
                norg = qr[0]

            zname = 'immutable' + settings.NONE_NAME
            nipz = IPzone(name=zname, organization=norg, ipaddrs=settings.LOCALHOST, creator="initialize_system")
            nipz.save()
            nipz.set_ipzone_marker()
            nipz.set_immutable(True)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":IPzone:" + str(nipz.name) + ":initialize_system"
            logger.info(msg)
            lh = Host(name=settings.NONE_NAME, ipaddr='0.0.0.0', ipzone_id=nipz.id)
            lh.save()
            nquota = Quota(name=settings.NONE_NAME, qid=0, creator="initialize_system")
            nquota.save()
            now = datetime.datetime.utcnow()
            msg = str(now) + ":Quota:" + str(nquota.name) + ":initialize_system"
            logger.info(msg)
            lhr = Restriction(name='localhost', readonly=True, usermapping='None', usermapid=0, do_not_delete=True,
                              creator="initialize_system")
            lhr.save()
            now = datetime.datetime.utcnow()
            msg = str(now) + ":Restriction:" + str(lhr.name) + ":initialize_system"
            logger.info(msg)
            lhr.set_organization(norg)
            lhr.ipzone = nipz
            lhr.individual_hosts.add(lh)
            lhr.save()

        dnsdomains = DNSdomain.objects.all()
        if dnsdomains.count() == 0:
            domain = "domain.org.tld"
            dnsd = DNSdomain(name=domain)
            dnsd.save()

            dnsd.get_dcs_from_msdcs()
            dnsd.save()

            if cluster.alive() is False:
                print("  could not connect to cluster " + str(cluster) + "  exiting!! ")
                sys.exit(-1)
            else:
                dcs = dnsd.get_windcs()
                for dc in dcs:
                    wdc = WinDC.objects.filter(name=dc)
                    if wdc.count() == 0:
                        wc = WinDC(name=dc, dnsdomain=dnsd)
                        wc.save()

        print("   cluster is " + str(cluster))

        # insure that a 'None' Quota exists -- it will be used when no quota is desired
        qr = Quota.objects.filter(name=settings.NONE_NAME)
        if qr.count() == 0:
            norg = Organization.objects.filter(name='#None')
            if norg.count() == 0:
                norg = Organization(name='#None')
                norg.save()
            else:
                norg = norg[0]
            nonequota = Quota(name=settings.NONE_NAME, size=0, creator="initialize_system")
            nonequota.save()
            nonequota.set_organization(norg)

        organizations = Organization.objects.get_queryset()
        # print("organizations: " + str(organizations))
        now = timezone.now() + datetime.timedelta(days=30)
        # print("now: " + str(now))
        for org in organizations:
            # print("calling " + str(org) + ".check_hosts() at " + str(now))
            state = org.check_hosts()
            # print(str(org) + ".check_hosts() returned " + str(state))
            # print("calling " + str(org) + ".check_ipzones() at " + str(now))
            state = org.check_ipzones()
            # print(str(org) + ".check_ipzones() returned " + str(state))

        dcs = WinDC.objects.all()
        # dcs = [WinDC.objects.first()]
        print("    dcs are: " + str(dcs))
        now = timezone.now() + datetime.timedelta(days=30)
        print("        now: " + str(now))
        for dc in dcs:
            state = dc.load_neworgs(cluster)
            orgs = dc.get_orgs()
            print("           " + str(dc) + ".load_neworgs( " + str(cluster) + " ) at " + str(now) + " returned " + str(
                state) + " and get_orgs found " + str(len(orgs)) + " orgs")

            if state is True:
                state = dc.load_newipzones()

            if state is True:
                ipzones = dc.get_ipzones()
                print("           " + str(dc) + ".load_newipzones() at " + str(now) + " returned " + str(
                    state) + " and found " + str(len(ipzones)) + " ipzones ")

            hosts = []
            if state is True:
                dc.load_newhosts()
                hosts = dc.get_hosts()
                print("           " + str(dc) + ".load_newhosts() at " + str(now) + " found " + str(
                    len(hosts)) + " hosts")

            if len(hosts) > 0:
                break

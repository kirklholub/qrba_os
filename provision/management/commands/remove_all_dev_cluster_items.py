#!/usr/bin/python
from __future__ import unicode_literals

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError
import sys
import datetime
from django.utils import timezone
from provision.models import IPzone, Clusterpath, Cluster, DNSdomain, Host, NfsExport, Organization, Quota, Report, \
    Restriction, Sysadmin, WinDC
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
    help = "Removes ALL nfsexport and shares (quotas) from the dev cluster"

    def handle(self, *args, **options):
        msg = "QRBA API version: " + str(settings.QUMULO_API_VERSION)
        print(msg)
        (conninfo, creds) = qlogin(settings.QUMULO_devcluster['ipaddr'], 'admin',
                                   settings.QUMULO_devcluster['adminpassword'], settings.QUMULO_devcluster['port'])
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name)
            logger.critical(msg)
            sys.exit(-1)
        qr = qumulo.rest.version.version(conninfo, None)
        msg = "cluster API version: " + str(qr)

        qr = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        if qr.count() == 0:
            cluster = Cluster(name=settings.QUMULO_devcluster['name'], ipaddr=settings.QUMULO_devcluster['ipaddr'],
                              adminpassword=settings.QUMULO_devcluster['adminpassword'],
                              port=settings.QUMULO_devcluster['port'])
            cluster.save()
        else:
            cluster = qr[0]

        msg = cluster.remove_all_cluster_items()
        print(msg)

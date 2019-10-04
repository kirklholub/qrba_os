#!/usr/local/bin/python2

import os
import sys
import fileinput

sys.path.append("/Users/holub/PycharmProjects/qrba")

# Import Qumulo REST libraries
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
import qumulo.lib.auth
import qumulo.lib.request
import qumulo.rest
from qrba import settings

import os, sys

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import datetime
from django.utils import timezone
from provision.models import Organization
import json


def login(host, user, passwd, port):
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
        print __doc__
        sys.exit(1)

    return (conninfo, creds)


class Command(BaseCommand):
    help = "installs an interface and network given config files"

    def add_arguments(self, parser):
        parser.add_argument('ifconfig', type=str)
        parser.add_argument('netconfig', type=str)

    def handle(self, *args, **options):
        ## Obtain REST credentials
        (conninfo, creds) = login(settings.QUMULO_devcluster['ipaddr'], 'admin',
                                  settings.QUMULO_devcluster['adminpassword'], settings.QUMULO_devcluster['port'])

        ifconfig = options['ifconfig']
        idata = ''
        for line in fileinput.input(ifconfig):
            idata = idata + str(line)
        ifdata = json.loads(idata)

        netconfig = options['netconfig']
        ndata = ''
        for line in fileinput.input(netconfig):
            ndata = ndata + str(line)
        netdata = json.loads(ndata)

        response = qumulo.rest.network.add_network(conninfo, creds, ifdata['id'])
        print("response: " + str(response))
        for iface in response.data:
            print("iface: " + str(iface))
            networks = qumulo.rest.network.list_networks(conninfo, creds, netdata)
            print("networks: " + str(networks))
            pass

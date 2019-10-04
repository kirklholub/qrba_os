#!/usr/bin/python
from __future__ import unicode_literals

import ast
import os
import sys
import json
import random
import datetime
import pytz

sys.path.append("/Users/holub/PycharmProjects/qrba")
os.environ["DJANGO_SETTINGS_MODULE"] = "qrba.settings"
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model

# https://stackoverflow.com/questions/19475955/using-django-models-in-external-python-script
from django.core.management.base import BaseCommand, CommandError

import fileinput
from provision.models import Activity, Cluster
import logging

logger = logging.getLogger('qrba.models')

from qrba import settings

# Qumulo REST libraries
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import qumulo.lib.auth
import qumulo.lib.request as request
import qumulo.rest

User = get_user_model()


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
        msg = "Error connecting to the REST server: %s" % excpt
        logger.critical(msg)

    return (conninfo, creds)


class Command(BaseCommand):
    help = "reads a formatted text file and loads host activity test data"

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str)
        parser.add_argument('days_in_dataset', type=str)

    def handle(self, *args, **options):

        creator_msg = "load_host_activity_test_data"
        (conninfo, creds) = qlogin(settings.QUMULO_devcluster['ipaddr'], 'admin',
                                   settings.QUMULO_devcluster['adminpassword'], 8000)
        if not conninfo:
            msg = "could not connect to dev cluster  ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        qr = Cluster.objects.filter(name=settings.QUMULO_devcluster['name'])
        if qr.count() == 0:
            cluster = Cluster(name=settings.QUMULO_devcluster['name'], ipaddr=settings.QUMULO_devcluster['ipaddr'],
                              adminpassword=settings.QUMULO_devcluster['adminpassword'], port=8000)
            cluster.save()
        else:
            cluster = qr[0]

        filename = options['filename']
        numdays = options['days_in_dataset']
        for d in range(int(numdays), 0, -1):
            data = ''
            for line in fileinput.input(filename):
                if "rate" in str(line):
                    # "rate": 1,
                    val = str(line).split(':')
                    val = val[1].replace(",", "")
                    val = float(val) * random.random()
                    line = '"rate": ' + str(val) + ","
                data = data + line
            data = json.loads(data)
            sample = request.RestResponse(data, 'etag')
            dt = datetime.datetime.utcnow()
            dt = dt.replace(tzinfo=pytz.UTC)
            dt = dt - datetime.timedelta(days=d)
            cluster.load_activity_sample(conninfo=conninfo, creds=creds, sample=sample, validtime=dt)

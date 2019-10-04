# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import ast
import commands
import datetime
import pytz
import fileinput
import json
import math
import os
import re
import socket
import sys
from smtplib import SMTPException

from django.db.models.signals import post_save
from django.dispatch import receiver

from ipaddr import IPv4Network

from django.db import models
from django.utils import timezone
from django.core.mail import send_mail
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.sessions.models import Session
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse

from qrba import settings

import logging

logger = logging.getLogger('qrba.models')

# Qumulo REST libraries
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import qumulo.lib.auth
import qumulo.lib.request as request
import qumulo.rest
from qumulo.rest.nfs import NFSRestriction
import qumulo.rest.quota as QRquota
import qumulo.rest.fs as fs


# https://www.w3resource.com/python-exercises/math/python-math-exercise-57.php
def sd_calc(data):
    n = len(data)
    if n <= 1:
        return 0.0
    mean, sd = avg_calc(data), 0.0

    # calculate stan. dev.
    for el in data:
        sd += (float(el) - mean) ** 2
    sd = math.sqrt(sd / float(n - 1))
    return sd


def avg_calc(ls):
    n, mean = len(ls), 0.0
    if n <= 1:
        return ls[0]

    # calculate average
    for el in ls:
        mean = mean + float(el)
    mean = mean / float(n)
    return mean


# user mapping and its inverse
UM_CHOICES = (('none', 'NFS_MAP_NONE'), ('root', 'NFS_MAP_ROOT'), ('all', 'NFS_MAP_ALL'))

#
SIZE_CHOICES = (('bt', 'Byte'), ('kb', 'KB'), ('mb', 'MB'), ('gb', 'GB'), ('tb', 'TB'), ('pb', 'PB'), ('eb', 'EB'))

CLUSTER_TIME_SERIES_CHOICES = (
    ('1', 'iops.read.rate'), ('2', 'iops.total.rate'), ('3', 'iops.write.rate'), ('4', 'reclaim.deferred.rate'),
    ('5', 'reclaim.snapshot.rate'), ('6', 'reclaim.total.rate'), ('7', 'throughput.read.rate'),
    ('8', 'throughput.total.rate'), ('7', 'throughput.write.rate'))

ACTIVITY_CHOICES = (
    ('1', 'file-iops-write'), ('2', 'file-throughput-read'), ('3', 'file-iops-read'), ('4', 'metadata-iops-read'),
    ('5', 'metadata-iops-write'), ('6', 'file-throughput-write'))

EVENT_CHOICES = (('0', 'unknown'), ('1', 'warning'), ('2', 'critical'), ('3', 'full'), ('4', 'filled'))

#
# CADENCE_CHOICES = ( ('m','Minutes'), ('h','Hours'), ('d','Days'), ('m','Monday'), ('t','Tuesday'),('w','Wednesday'), ('th','Thursday'),('f','Friday'),('sa','Saturday'),('su','Sunday') )
CADENCE_CHOICES = (('m', 'Minutes'), ('h', 'Hours'), ('d', 'Days'))
DAYS_IN_DATASET = (
('0', 'sub-daily'), ('1', 'daily'), ('7', 'weekly'), ('30', 'monthly'), ('90', 'three month'), ('180', 'six month'),
('365', 'yearly'))


def unicode_to_datetime(dt):
    # 1970-01-01T01:01:01+0000
    if 'T' in str(dt):
        dt = dt[0:19]
        msg = "dt: " + str(dt)
        # logger.debug(msg)
        dt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
        dt = dt.replace(tzinfo=pytz.UTC)
        msg = " now dt = " + str(dt)
        # logger.debug(msg)

    #    0001-01-01 00:00:01Z
    if 'Z' in str(dt):
        dt = dt[0:18]
        msg = "dt: " + str(dt)
        # logger.debug(msg)
        dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=pytz.UTC)
        msg = " now dt = " + str(dt)
        # logger.debug(msg)
    return dt


def convert_nfs_user_mapping(name):
    convert = {
        'none': 'NFS_MAP_NONE',
        'root': 'NFS_MAP_ROOT',
        'all': 'NFS_MAP_ALL',
        'nfs_map_none': 'NFS_MAP_NONE',
        'nfs_map_root': 'NFS_MAP_ROOT',
        'nfs_map_all': 'NFS_MAP_ALL',
    }

    if name.lower() not in convert:
        raise ValueError('%s is not one of none, root, or all' % (name))
    return convert[name.lower()]

def email_from_orgname(orig):
    org = str(orig)
    try:
        settings.LEGACY_TO_NEW_ORGANIZATIONS[org]
        org = settings.LEGACY_TO_NEW_ORGANIZATIONS[org]
    except:
        pass

    # email format to contact sysadmins from a given branch
    email = "sys." + org + ".branch@tld.org"

    # for a special case 
    if 'specialorg' in org:
        email = "some_special_admin_email@tld.org"

    return email


def get_zoneinfo_from_iplist(name, iplist):
    """
    Searches iplist of occurances of IPZONE_MARKER_BASE and returns an zoneinfo object
    :param name:
    :param iplist:
    :return: a zoneinfo object keyed by ip addresses beginning with IPZONE_MARKER_BASE and containing the ipzone name and its ip address list
    """
    # get ipzone markers to beginning of list -- luckily 10.x.y.z will always be ahead of 1ab.x.y.z  -- NOT TRUE  10.1* comes before 10.2*  !!
    iplist.sort()
    markerset = set()
    hostset = set()
    for ip in iplist:
        if settings.IPZONE_MARKER_BASE in ip:
            markerset.add(ip)
        else:
            hostset.add(ip)

    iplist = []
    hostlist = []
    markerlist = []
    for m in markerset:
        markerlist.append(m)
    for h in hostset:
        hostlist.append(h)

    markerlist.sort()
    hostlist.sort()
    for m in markerlist:
        iplist.append(m)
    for h in hostlist:
        iplist.append(h)

    current = str(iplist[0]).strip().encode('ascii', 'ignore')
    zoneinfo = {}
    ipzmarkers = set()
    for ip in iplist:
        ip = str(ip).strip().encode('ascii', 'ignore')
        if settings.IPZONE_MARKER_BASE in ip:
            try:
                test = zoneinfo[ip]
            except:
                zoneinfo[ip] = {}
                zoneinfo[ip]['name'] = name
                zoneinfo[ip]['ipaddrs'] = set()
                zoneinfo[ip]['ipaddrs'].add(ip)

            ipzmarkers.add(ip)
            current = ip
        else:
            if settings.IPZONE_MARKER_BASE in current:
                zoneinfo[current]['ipaddrs'].add(ip)

    for ipzm in ipzmarkers:
        ipzmsize = ipzm.split(".")
        if len(ipzmsize) > 3:
            ipzm = str(ipzm).strip().encode('ascii', 'ignore')
            qs = IPzone.objects.filter(ipzmarker=ipzm)
            if qs.count() != 1:
                msg = "   could not find IPZone for marker " + str(ipzm) + " -- iplist is " + str(iplist)
                # logger.debug(msg)
            else:
                zoneinfo[ipzm]['name'] = qs[0].name
                # msg = "   found IPZone for marker " + str(ipzm) + " name is " + str(zoneinfo[ipzm]['name']) + ",  iplist is " + str(iplist)
                msg = "   found IPZone for marker " + str(ipzm) + " name is " + str(zoneinfo[ipzm]['name'])
                #logger.debug(msg)

    # case for no markers present
    if len(ipzmarkers) == 0:
        zoneinfo['0.0.0.0'] = {}
        zoneinfo['0.0.0.0']['name'] = name
        zoneinfo['0.0.0.0']['ipaddrs'] = iplist

    msg = "  zoneinfo is " + str(zoneinfo) + " for iplist " + str(iplist)
    # logger.info(msg)
    return zoneinfo

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


#########################################################################################################
#     ___                        _          _   _             _____          _            _             #
#    / _ \ _ __ __ _  __ _ _ __ (_)______ _| |_(_) ___  _ __ | ____|_  _____| | _   _  __| | ___  ___   #
#   | | | | '__/ _` |/ _` | '_ \| |_  / _` | __| |/ _ \| '_ \|  _| \ \/ / __| || | | |/ _` |/ _ \/ __|  #
#   | |_| | | | (_| | (_| | | | | |/ / (_| | |_| | (_) | | | | |___ >  < (__| || |_| | (_| |  __/\__ \  #
#    \___/|_|  \__, |\__,_|_| |_|_/___\__,_|\__|_|\___/|_| |_|_____/_/\_\___|_| \__,_|\__,_|\___||___/  #
#              |___/                                                                                    #
#########################################################################################################

class OrganizationExcludes(models.Model):
    ''' A string of organizations that do not have UNIX hosts  '''
    excludes = "UNIX Service Domain Controllers No Policy MAC_CAC NETADM Windows Servers Test " \
               "FDCC_no_NLA Restricted OU Zone User Provisioning Groups Admin Groups FDCC_CAC FDCC " \
               "No FW FDCC_Computers Linux_CAC Vaisala MacSC_Test Users NO NTLM DO Admin Rights Salt " \
               "SOMESTRING SOMESTRINGTest"

    def get_excludes(self):
        return self.excludes

    def set_excludes(self, exlist):
        excludes = ''
        for x in exlist:
            excludes = x + " " + excludes
        self.save()

    def add_excludes(self, exlist):
        excludes = ''
        for x in exlist:
            excludes = x + " " + excludes
        self.excludes = excludes + self.excludes
        self.save()

    def delete_excludes(self, exlist):
        excludes = ''
        for x in exlist:
            self.excludes = re.sub(x, "", excludes)
        self.save()


#######################################
#     ____ _           _              #
#    / ___| |_   _ ___| |_ ___ _ __   #
#   | |   | | | | / __| __/ _ \ '__|  #
#   | |___| | |_| \__ \ ||  __/ |     #
#    \____|_|\__,_|___/\__\___|_|     #
#                                     #
#######################################

class Cluster(models.Model):
    name = models.CharField(max_length=150)
    ipaddr = models.CharField(max_length=50)
    port = models.IntegerField(default=8000)
    adminname = models.CharField(max_length=50, null=True, default='admin')
    adminpassword = models.CharField(max_length=50, null=True, default='setme')
    updated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # logger.debug("saving cluster: " + str(self.name))
        super(Cluster, self).save(*args, **kwargs)
        # now = datetime.datetime.utcnow()
        # msg = str(now) + ":superCluster:" + str(self.name) + ":no_updater"
        # logger.info(msg)

    def alive(self):
        '''  returns True if connection to the server is OK and False otherwise  '''
        state = False

        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        try:
            msg = "   conninfo: " + str(conninfo)
            if creds:
                state = True
            else:
                msg = msg + "\n" + "      CREDENTIALS ERROR -- creds: " + str(creds)
                logger.critical(msg)
        except socket.error as err:
            msg = "   socket error connecting to " + str(self.ipaddr) + " : " + str(err)
            logger.critical(msg)
        return state

    def fetch_qumulo_shares(self, src_cluster):
        '''  returns a list of qumulo 'quota' objects mapped into dictionaries  '''
        if src_cluster == None:
            src_cluster = self

        shares = []
        (conninfo, creds) = qlogin(src_cluster.ipaddr, src_cluster.adminname, src_cluster.adminpassword,
                                   src_cluster.port)
        if conninfo:
            qpi = qumulo.rest.quota.get_all_quotas_with_status(conninfo, creds, page_size=10000)
            for q in qpi.next():
                q = str(q)
                if 'None' in q:
                    break
                q = q.replace("u'", "'", 100)
                ale = ast.literal_eval(q)
                for x in ale['quotas']:
                    x['path'] = str(x['path']).replace('\n', '')
                    xd = dict(x)
                    shares.append(xd)
        # msg = "    found " + str(len(shares)) + " shares on cluster " + str(src_cluster)
        # logger.debug(msg)
        return shares

    def size_and_units_from_qshares_limit(self, qlimit):
        size = qlimit
        units = 'bt'
        if size > 1000:
            size = float(size) / float(1000)
            units = 'kb'
        if size > 1000:
            size = float(size) / float(1000)
            units = 'mb'
        if size > 1000:
            size = float(size) / float(1000)
            units = 'gb'
        if size > 1000:
            size = float(size) / float(1000)
            units = 'tb'
        if size > 1000:
            size = float(size) / float(1000)
            units = 'pb'
        if size > 1000:
            size = float(size) / float(1000)
            units = 'xb'
        return (size, units)

    def sync_clusterpaths_from_cluster(self, src_cluster):
        '''
        synchronizes clusterpaths from the source cluster to self.cluster.
        Clusterpath and Quota objects are created or updated as needed.
        Directories and shares self.cluster.ipaddr are created
        Returns an activities hash in which len(ok) should equal len(added) + len(updated).
        Therefore, 'out_of_sync' should always be a zero length list.

        '''

        added = []
        out_of_sync = []
        updated = []
        up_to_date = []
        activity = {'added': added, 'out_of_sync': out_of_sync, 'updated': updated, 'up_to_date': up_to_date}

        creator_msg = "sync_clusterpaths_from_" + str(src_cluster) + "_to_" + str(self)
        
        # fetch clusterpaths on the source cluster
        qumulo_shares = self.fetch_qumulo_shares(src_cluster)
        msg = "   received " + str(len(qumulo_shares)) + " qumulo_shares"
        # logger.debug(msg)

        msg = "qclusterpaths: " + str(qumulo_shares)
        # logger.debug(msg)

        nfs_qinfo = self.fetch_nfs_quota_info(src_cluster)
        msg = "\nnfs_qinfo:\n" + str(nfs_qinfo)
        # logger.debug(msg)

        # Deal with exports which do no have a quota
        qumulo_shares_to_keep = []
        for i in nfs_qinfo:
            for qs in qumulo_shares:
                if qs['path'] == i['path']:
                    qumulo_shares_to_keep.append(qs)
                    continue


        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + " ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        for qshare in qumulo_shares:
            thisid = qshare['id']
            # default size units are GB
            # thislimit = float(qshare['limit']) / float(settings.QUOTA_1GB)
            qlimit = qshare['limit']
            (size_in_units, units) = self.size_and_units_from_qshares_limit(qlimit)
            thisusage = qshare['capacity_usage']
            thisname = str(qshare['path']).strip().encode('ascii', 'ignore')
            orgname = thisname.encode('ascii', 'ignore')
            if settings.QUMULO_BASE_PATH in orgname:
                orgname = orgname.replace(settings.QUMULO_BASE_PATH, "")
                orgname = orgname.split('/')
                orgname = str(orgname[1]).encode('ascii', 'ignore')

            # if orgname == 'its' or orgname == 'data':
            #    delete_state = True
            # else:
            #    delete_state = False
            delete_state = False

            msg = " searching for cp with dirpath " + str(thisname)
            #logger.info(msg)
            cpsearch = Clusterpath.objects.filter(dirpath=thisname, cluster_id=self.id)
            if cpsearch.count() > 0:
                cpsearch = cpsearch[0]
                msg = "  found cp " + str(cpsearch)
                #logger.info(msg)
                need_to_update = False
                thisquota = cpsearch.quota
                # if cpsearch.dirid < 0:
                #    cpsearch.set_dirid(0)
                if float(thisquota.size) != float(size_in_units):
                    msg = "  float(thisquota.size) != float(size_in_units).... "
                    logger.info(msg)
                    msg = "    qlimit = " + str(qlimit) + " for qshare[ " + str(thisid) + " ]"
                    logger.info(msg)
                    msg = "    thisquota.size = " + str(thisquota.size) + " for thisquota " + str(thisquota)
                    logger.info(msg)
                    msg = "    size_in_units = " + str(size_in_units)
                    logger.info(msg)
                    thisquota.set_size(size_in_units)
                    msg = "    thisquota.size now = " + str(thisquota.size) + " for thisquota " + str(thisquota)
                    logger.info(msg)
                    thisquota.units = units
                    need_to_update = True
                    if self == src_cluster:
                        msg = "      NEED TO UPDATE quota on src_cluster " + str(src_cluster)
                    else:
                        msg = "      self is not src_cluster " + str(self) + ", " + str(src_cluster)
                    logger.info(msg)

                else:
                    msg = "   OK -- thisquota.size == size_in_units == " + str(size_in_units)
                    logger.info(msg)

                qusage = thisquota.get_usage()
                # msg = "thisusage = " + str(thisusage) + " for thisquota " + str(thisquota)
                # logger.info(msg)
                # msg = "qusage = " + str(qusage)
                # logger.info(msg)
                if int(thisquota.get_usage()) != int(thisusage) and settings.NONE_NAME not in str(thisquota.name):
                    thisquota.set_usage(thisusage)
                    thisquota.set_pctusage()
                    need_to_update = True
                    #if need_to_update is True:
                    # update my usage object -- so that a time series of usage can be constructed
                    thisqusage = QuotaUsage(size=qlimit, usage=thisusage, quota=thisquota)
                    thisqusage.save()
                    thisquota.set_usage(thisusage)
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addQuotaUsage:" + str(thisquota.name) + ":" + creator_msg
                    logger.info(msg)
                    thisqusage.set_organization(thisquota.organization)
                    updated.append(thisquota.name)
                else:
                    up_to_date.append('quota ' + thisquota.name)

            # if cpsearch.count() <= 0
            else:
                try:
                    fileattrs = fs.get_file_attr(conninfo, creds, thisname)
                    thisid = int(fileattrs.lookup('id'))
                    msg = "      thisid = " + str(thisid) + " for thisname " + str(thisname)
                    #logger.debug(msg)
                except qumulo.lib.request.RequestError as err:
                    msg = "         RequestError: " + str(err) + " at get_file_attr for thisname >" + str(
                        thisname) + "<"
                    #logger.debug(msg)

                qname = thisname
                msg = "    thisname is " + str(thisname) + " and thisid is " + str(thisid)
                #logger.debug(msg)

                qid = self.create_directory_on_cluster(conninfo, creds, qname)
                msg = "   qid is " + str(qid) + " for " + str(qname)
                #logger.debug(msg)

                thisquota = Quota.objects.filter(name=qname)
                if thisquota.count() == 0:
                    thisquota = Quota(qid=qid, name=qname, size=size_in_units, usage=thisusage, units=units,
                                      do_not_delete=delete_state, creator=creator_msg)
                    msg = "       creating Quota " + str(thisquota) + " with size = " + str(
                        size_in_units) + " " + str(units) + " and usage = " + str(thisusage)
                    # logger.info(msg)
                    thisquota.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addQuota:" + str(thisquota.name) + ":" + creator_msg
                    logger.info(msg)
                    thisquota.set_pctusage()
                    thisqusage = QuotaUsage(size=qlimit, usage=thisusage, quota=thisquota)
                    thisqusage.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addQuotaUsage:" + str(thisquota.name) + ":" + creator_msg
                    logger.info(msg)

                    # msg = self.create_quota_on_cluster(conninfo, creds, qid, qname, qlimit)
                    msg = "  NOT CALLING self.create_quota_on_cluster(conninfo, creds, qid = " + str(
                        qid) + ", qname = " + str(qname) + " , qlimit = " + str(qlimit) + ")"
                    logger.info(msg)
                else:
                    thisquota = thisquota[0]
                    thisquota.usage = thisusage
                    thisquota.save()
                    thisquota.set_pctusage()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":updated_usage_to_" + str(thisusage) + "_for_Quota:" + str(
                        thisquota.name) + ":" + creator_msg
                    logger.info(msg)
                    msg = "      found thisquota " + str(thisquota)
                    # logger.info(msg)
                    # msg = self.update_quota_on_cluster(conninfo, creds, qid, qname, qlimit)
                    msg = "  NOT CALLING self.update_quota_on_cluster(conninfo, creds, qid = " + str(
                        qid) + ", qname = " + str(qname) + " , qlimit = " + str(qlimit) + ")"
                    logger.info(msg)
                    quqs = QuotaUsage.objects.filter(quota=thisquota)
                    if quqs.count() == 0:
                        thisqusage = QuotaUsage(size=qlimit, usage=thisusage, quota=thisquota)
                        thisqusage.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addQuotaUsage:" + str(thisquota.name) + ":" + creator_msg
                        logger.info(msg)
                    else:
                        thisqusage = quqs[0]

                msg = "      searching for clusterpath dirid = " + str(thisid) + " and cluster_id = " + str(self.id)
                #logger.debug(msg)

                thiscp = Clusterpath.objects.filter(dirid=thisid, cluster_id=self.id)
                if thiscp.count() == 0:
                    msg = "    creating clusterpath for dirid = " + str(thisid) + " and quota " + str(
                        thisquota) + " on cluster " + str(self)
                    #logger.debug(msg)
                    newcp = Clusterpath(dirid=thisid, dirpath=thisname, quota=thisquota, cluster_id=self.id,
                                        do_not_delete=delete_state, creator=creator_msg)
                    newcp.save(create_on_cluster=True)
                    added.append(str(newcp))
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addClusterpath:" + str(thisname) + ":" + creator_msg
                    logger.info(msg)
                else:
                    msg = "   thiscp.count() != 0 == " + str(thiscp.count()) + " for dirid " + str(
                        thisid) + " and clusterid = " + str(self.id)
                    #logger.debug(msg)
                    newcp = thiscp[0]

                # Organization may not exist
                # orgname = thisname.encode('ascii', 'ignore')
                # if settings.QUMULO_BASE_PATH in orgname:
                ##    orgname = orgname.replace(settings.QUMULO_BASE_PATH, "")
                #    orgname = orgname.split('/')
                #    orgname = str(orgname[1]).encode('ascii', 'ignore')
                org = Organization.objects.filter(name=orgname)
                if org.count() == 0:
                    thisorg = Organization(name=orgname)
                    thisorg.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addOrganization:" + str(orgname) + ":" + creator_msg
                    logger.info(msg)
                else:
                    thisorg = org[0]

                # add this cp to the org and this org to the new cp
                thisorg.clusterpaths.add(newcp)
                newcp.set_organization(thisorg)

                # set the primary email address based on the organization
                addr = email_from_orgname(thisorg.name)
                thisquota.set_primary_email(addr)

                try:
                    hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS[str(thisorg)]
                except:
                    hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS['default']
                thisorg.set_adminhosts(hostlist)
                if thisusage:
                    thisqusage.set_organization(thisorg)

        '''  Sanity check -- Clusterpaths and Quotas should now be in sync! '''
        for cp in Clusterpath.objects.all():
            for qshare in qumulo_shares:
                # msg = "        qcp is " + str(qcp) + " --- qcpid = " + str(qcp['id'])
                # logger.debug(msg)
                # if id, limit, and usage all match, all is up to date
                if int(qshare['id']) == int(cp.dirid):
                    if (int(qshare['limit']) == int(cp.quota.size) and
                            int(qshare['capacity_usage']) == int(cp.quota.usage)):
                        # quotas match
                        up_to_date.append(cp.dirpath)
                    else:
                        out_of_sync.append(cp.dirpath)
        return activity

    def create_directory_on_cluster(self, conninfo, creds, dirpath):
        # msg = "   in create_directory_on_cluster -- self is " + str(self) + " and -- dirpath = " + str(dirpath)
        # logger.debug(msg)

        try:
            pattrs = fs.get_file_attr(conninfo, creds, dirpath)
            pid = int(pattrs.lookup('id'))
            # msg = "      found pid " + str(pid) + " for path >" + str(dirpath) + "<"
            # logger.debug(msg)
        except qumulo.lib.request.RequestError as err:
            # msg = "      RequestError: " + str(err) + " for path >" + str(dirpath) + "<"
            # logger.debug(msg)

            parent = "/"
            path = parent
            pid = -1
            for d in dirpath.split('/'):
                msg = "     d is " + str(d) + " and parent is " + str(parent)
                #logger.debug(msg)
                if d == '':
                    msg = "       skipping d >" + str(d) + "<"
                    #logger.debug(msg)
                    parent = parent + d
                    continue

                if path == "/":
                    path = "/" + d
                else:
                    path = path + '/' + d
                msg = "     path is now: " + str(path)
                #logger.debug(msg)

                try:
                    pattrs = fs.get_file_attr(conninfo, creds, path)
                    pid = int(pattrs.lookup('id'))
                    # msg = "      pid is " + str(pid) + " for path >" + str(path) + "<"
                    # logger.debug(msg)
                except qumulo.lib.request.RequestError as err:
                    pid = -1
                    # msg = "      RequestError: " + str(err) + " -- pid set to " + str(pid) + " for path >" + str(path) + "<"
                    # logger.debug(msg)

                if pid < 1:
                    # msg = "     creating directory >" + str(d) + "< in parent >" + str(parent) + "<"
                    # logger.debug(msg)
                    try:
                        qr = fs.create_directory(conninfo, creds, d, parent)
                        # msg = "     after create directory d >" + str(d) + "< in parent >" + str(parent) + "<"
                        # logger.debug(msg)
                        # msg = "       qr = " + str(qr)
                        # logger.debug(msg)
                        pid = qr.lookup('id')
                        # msg = "       pid is " + str(pid) + " for d >" + str(d) + "<"
                        # logger.debug(msg)
                    except qumulo.lib.request.RequestError as err:
                        # msg = "       RequestError: " + str(err) + " at create directory d >" + str(
                        #    d) + "< for parent " + str(parent)
                        # logger.debug(msg)
                        pass

                parent = path
            # msg = "      created directory " + str(dirpath) + " on self.id = " + str(self.id) + "  -- pid is " + str(
            #    pid)
            # logger.debug(msg)
        return pid

    def delete_directory_on_cluster(self, conninfo, creds, dirpath):
        '''
        removes the given directory path from the cluster element by element
        :param conninfo:
        :param creds:
        :param dirpath:
        :return:
        '''
        # msg = "   in delete_directory_on_cluster -- self is " + str(self) + " and -- dirpath = " + str(dirpath)
        # logger.debug(msg)

        try:
            pathparts = dirpath.split('/')
            while len(pathparts) > 0:
                path = ''
                for i in pathparts:
                    path = path + '/' + i
                path = path.replace('//', '/')
                if not os.path.isfile(path):
                    qr = fs.delete_tree(conninfo, creds, path)
                else:
                    msg = "   path " + str(path) + " is a file -- not removing"
                    #logger.debug(msg)
                    logger.info(msg)
                    logger.critical(msg)
                    break
                pathparts.remove(pathparts[len(pathparts) - 1])


        except qumulo.lib.request.RequestError as err:
            msg = "      RequestError: " + str(err) + " at fs.delete_tree for dirpath >" + str(dirpath) + "<"
            #logger.debug(msg)

        try:
            qr = fs.tree_delete_status(conninfo, creds, dirpath)
            msg = "   error deleting dirpath " + str(dirpath) + " .. qr is " + str(qr)
        except qumulo.lib.request.RequestError as err:
            # msg = "      RequestError: " + str(err) + " for dirpath >" + str(dirpath) + "<"
            msg = "deleted directory " + str(dirpath)

        #logger.debug(msg)
        return msg

    def create_quota_on_cluster(self, conninfo, creds, cid, path, limit):
        msg = "       creating new quota for path >" + str(path) + "< and cid = " + str(cid) + " and limit " + str(
            limit)
        #logger.debug(msg)
        limit = int(limit)
        try:
            qr = QRquota.create_quota(conninfo, creds, cid, limit)
            qid = qr.lookup('id')
            msg = '         created quota_' + str(path) + " for id " + str(cid) + ", qid:" + str(qid)
        except qumulo.lib.request.RequestError as err:
            msg = "       RequestError: " + str(err) + " at create_quota_on_cluster for cid " + str(
                cid) + " and path >" + str(path) + "< -- qid:-1"
        #logger.debug(msg)
        return msg

    def update_quota_on_cluster(self, conninfo, creds, cid, path, limit):
        # msg = '       updating quota_' + str(id) + " for dirpath >" + str(path) + "< and cid " + str(
        #    cid) + " with limit " + str(limit)
        # logger.debug(msg)
        if cid == 0:
            msg = "qid:0"
            return msg

        try:
            qr = QRquota.update_quota(conninfo, creds, cid, limit)
            qid = qr.lookup('id')
            msg = "        updated quota_" + str(cid) + " to size " + str(limit) + " for path >" + str(
                path) + "< -- qid:" + str(qid)
        except qumulo.lib.request.RequestError as err:
            msg = "        RequestError: " + str(err) + " at update_quota_on_cluster " + str(cid) + " and path >" + str(
                path) + "< -- qid:-1"
        return (msg)

    def delete_quota_on_cluster(self, conninfo, creds, id, path):
        # msg = "       deleting quota for path >" + str(path) + "< and id = " + str(id)
        #logger.debug(msg)
        try:
            qr = QRquota.delete_quota(conninfo, creds, id)
            # msg = "len(qr) is " + str(len(qr))
            # print(msg)
            msg = "   qr is >" + str(qr) + "<"
            # response body for deletion is ""  (two double quotes so len is 2)
            if len(qr) == 2:
                msg = '      deleted quota_' + str(path) + " for id " + str(id)
            else:
                msg = '      in delete_quota -- qr not null for id = ' + str(id) + " and path " + str(
                    path) + " .. qr = " + str(qr)
        except qumulo.lib.request.RequestError as err:
            msg = "       RequestError: " + str(err) + " at delete_quota_on_cluster for id " + str(
                id) + " and path >" + str(path) + "< -- qid:-1"
        return msg

    def sync_clusterpaths_to_cluster(self, target):
        '''
        synchronizes all clusterpath objects from target.cluster to self.cluster
        Clusterpath and Quoto object are created on target.cluster.
        Directories and shares are also created on the target.cluster.ipaddr

        self as target is supported

        '''
        # msg = " self.id is " + str(self.id)
        # logger.debug(msg)
        # msg = " target.id is " + str(target.id)
        #logger.debug(msg)

        added = []
        updated = []
        out_of_sync = []
        ok = []
        activity = {'added': added, 'updated': updated, 'out_of_sync': out_of_sync, 'ok': ok}

        creator_msg = "sync_clusterpaths_to_" + str(target) + "_to_" + str(self)

        (targetconninfo, targetcreds) = qlogin(target.ipaddr, target.adminname, target.adminpassword, target.port)
        if not targetconninfo:
            msg = "could not connect to cluster " + str(target.name) + " ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        targetclusterpaths = self.fetch_qumulo_shares(target)
        #logger.debug("     targetclusterpaths: " + str(targetclusterpaths) + "\n-------\n\n")

        clusterpath_by_dirpath = {}
        for c in targetclusterpaths:
            clusterpath_by_dirpath[str(c['path'])] = int(c['id'])

        msg = "clusterpath_by_dirpath: " + str(clusterpath_by_dirpath)
        #logger.debug(msg)

        allclusterpaths = Clusterpath.objects.filter(cluster_id=self.id)
        # msg = "allclusterpaths: " + str(allclusterpaths)
        #logger.debug(msg)

        for cp in allclusterpaths:
            # msg = "cp = " + str(cp)
            #logger.debug(msg)

            dirpath = cp.dirpath.encode('ascii', 'ignore')
            # msg = "  dirpath is " + str(dirpath)
            # logger.debug(msg)
            # msg = "    dirid is " + str(cp.dirid)
            # logger.debug(msg)

            qname = cp.dirid
            # msg = "    qname is " + str(qname) + " and cp.dirid is " + str(cp.dirid)
            # logger.debug(msg)

            thisquota = Quota.objects.filter(name=qname)
            if thisquota.count() == 0:
                thisquota = Quota(qid=cp.dirid, name=qname, size=cp.quota.size, usage=cp.quota.usage,
                                  do_not_delete=True, creator=creator_msg)
                msg = "       creating Quota " + str(thisquota) + " with size = " + str(
                    cp.quota.size) + " and usage = " + str(
                    cp.quota.usage)
                thisquota.save()
                thisquota.set_pctusage()
                thisqusage = QuotaUsage(size=cp.quota.size, usage=cp.quota.usage, quota=thisquota)
                thisqusage.save()
                now = datetime.datetime.utcnow()
                msg = str(now) + ":addQuotaUsage:" + str(thisquota.name) + ":" + creator_msg
                logger.info(msg)
            else:
                thisquota = thisquota[0]
                msg = "      found thisquota " + str(thisquota)
                thisqusage = False
            # logger.debug(msg)

            msg = "      searching for clusterpath dirid = " + str(cp.dirid) + " and cluster_id = " + str(target.id)
            # logger.debug(msg)

            thiscp = Clusterpath.objects.filter(dirpath=cp.dirpath, cluster_id=target.id)
            if thiscp.count() == 0:
                # msg = "    creating clusterpath for dirpath = " + str(cp.dirpath) + " and quota " + str(
                #    thisquota) + " on cluster " + str(target)
                # logger.debug(msg)
                newcp = Clusterpath(dirpath=cp.dirpath, quota=thisquota, cluster_id=target.id, do_not_delete=True,
                                    creator=creator_msg)
                newcp.save(create_on_cluster=True)
                now = datetime.datetime.utcnow()
                msg = str(now) + ":addClusterpath:" + str(cp.dirpath) + ":" + creator_msg
                logger.info(msg)
                added.append(str(newcp))
            else:
                # msg = "   thiscp.count() != 0 == " + str(thiscp.count()) + " for dirid " + str(
                #    cp.dirid) + " and clusterid = " + str(target.id)
                # logger.debug(msg)
                newcp = thiscp[0]

            # Organization may not exist
            orgname = cp.dirpath
            if settings.QUMULO_BASE_PATH in orgname:
                orgname = orgname.replace(settings.QUMULO_BASE_PATH, "")
            else:
                orgname = "/" + cp.dirpath
            orgname = orgname.split('/')[0]
            org = Organization.objects.filter(name=orgname)
            # msg = "     org = " + str(org) + " for orgname = " + str(orgname)
            # logger.debug(msg)
            if org.count() == 0:
                thisorg = Organization(name=orgname)
                thisorg.save()
                now = datetime.datetime.utcnow()
                msg = str(now) + ":addOrganization:" + str(orgname) + ":" + creator_msg
                logger.info(msg)
                thisorg.clusterpaths.add(newcp)
                thisorg.save()
            else:
                thisorg = org[0]
            try:
                quotasize = settings.ORGANIZATION_QUOTA_LIMITS[orgname]
                units = 'tb'
            except:
                quotasize = settings.DEFAULT_CLUSTER_QUOTA_LIMIT
                units = 'pb'
            cp.quota.set_size(quotasize)
            cp.quota.set_units(units)
            #msg = "    quotasize is " + str(quotasize) + " for orgname " + str(orgname)
            #logger.debug(msg)

            try:
                hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS[str(thisorg)]
            except:
                hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS['default']

            #logger.debug(msg)
            thisorg.set_adminhosts(hostlist)
            newcp.set_organization(thisorg)

            # set the primary email address based on the organization
            addr = email_from_orgname(thisorg.name)
            thisquota.set_primary_email(addr)

            if thisqusage is not False:
                thisqusage.set_organization(thisorg)

            #logger.debug("...\n\n")
        return activity

    def fetch_nfs_quota_info(self, src_cluster):
        qinfo = []
        for nfsx in self.fetch_nfs_shares(src_cluster):
            q = {}
            q['capacity_usage'] = str('0')
            q['limit'] = str('0')
            if settings.QUMULO_BASE_PATH not in nfsx['fs_path']:
                q['path'] = settings.QUMULO_BASE_PATH + "/" + nfsx['fs_path']
            else:
                q['path'] = nfsx['fs_path']
            q['id'] = nfsx['id']
            qinfo.append(q)
        return qinfo


    def fetch_nfs_shares(self, src_cluster):
        '''
        returns a list of qumulo nfs 'share' objects
        '''
        nfs_shares = []

        (conninfo, creds) = qlogin(src_cluster.ipaddr, 'admin', src_cluster.adminpassword, src_cluster.port)
        try:
            shares = qumulo.rest.nfs.nfs_list_shares(conninfo, creds)
            for s in shares:
                if type(s) is list:
                    for x in s:
                        nfs_shares.append(x)
        except socket.error as err:
            msg = "   socket.error = " + str(err) + " at fetch_nfs_shares for src_cluster " + str(
                src_cluster) + " -- exiting now!!"
            logger.critical(msg)
            sys.exit(-1)
        return nfs_shares

    def fetch_an_nfs_share(self, conninfo, creds, shareid):
        '''
        returns the qumulo nfs 'share' object with id shareid
        '''
        nfs_share = ''
        try:
            share = qumulo.rest.nfs.nfs_list_share(creds, conninfo, shareid)
            if type(share) is list:
                nfs_share = share
        except socket.error as err:
            msg = "   socket.error = " + str(err) + " at fetch_nfs_shares for cluster " + str(
                self) + " -- exiting now!!"
            logger.critical(msg)
            sys.exit(-1)
        return nfs_share

    def delete_nfsexport_on_cluster(self, conninfo, creds, xid=0):
        try:
            qpi = qumulo.rest.nfs.nfs_delete_share(conninfo, creds, id_=xid )
            msg = '      deleted nfs exportid ' + str(xid)
        except qumulo.lib.request.RequestError as err:
            msg = "       RequestError: " + str(err) + " at delete_nfsexport_on_cluster for id >" + str(xid) + "<"
        #logger.debug(msg)
        return msg

    def sync_nfs_exports_from_cluster(self, src_cluster):
        '''
        Synchronizes nfs exports from the source cluster src_cluster to self.
        Quota, IPzone, and Restriction objects are created or updated as needed.
        Returns and activities hash in which len(added) should equal len(ok).
        Therefore, 'out_of_sync' should always be a zero length list.
        '''
        added = []
        updated = []
        out_of_sync = []
        ok = []
        activity = {'added': added, 'updated': updated, 'out_of_sync': out_of_sync, 'ok': ok}

        creator_msg = "sync_nfs_exports_from_" + str(src_cluster) + "_to_" + str(self)

        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + " ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        # get list of exiting exports by their directory id
        nfssearch_by_cpid = {}
        existing_exports = []

        for nfssearch in NfsExport.objects.all():
            #logger.debug("      nfsearch: " + str(nfssearch))
            cpdirid = nfssearch.clusterpath.dirid
            cpath = Clusterpath.objects.filter(dirid=cpdirid, cluster_id=self.id)
            #logger.debug("         cpath: " + str(cpath) + " and self.id = " + str(self.id) )
            if cpath.count() > 0:
                msg = "   cpath[0].cluster_id = " + str(cpath[0].cluster_id) + " and self.id = " + str(self.id)
                #logger.debug(msg)
                if cpath[0].cluster_id == self.id:
                    nfssearch_by_cpid[int(cpath[0].id)] = int(nfssearch.exportid)
                    existing_exports.append(int(nfssearch.exportid))
                # else:
                # msg = "  skipping ..."
                #logger.debug(msg)
            #else:
            #    logger.debug("      cpath.count = " + str(cpath.count))

        msg = "    existing_exports: " + str(existing_exports)
        #logger.debug(msg)

        myshares = self.fetch_nfs_shares(self)
        # logger.debug("     myshares:\n")
        # i = int(1)
        # for s in myshares:
        #    msg = str(i) + ": " + str(s) + "\n" + msg
        #    i = i + int(1)
        #logger.debug(msg)

        shares = self.fetch_nfs_shares(src_cluster)
        # logger.debug("     shares:\n")

        # msg = "\n"
        # i = int(1)
        # for s in shares:
        #    msg = msg + str(i) + ": " + str(s) + "\n"
        #    i = i + int(1)
        #logger.debug(msg)

        # loop through share info returned from qumulo
        i = int(1)
        for s in shares:
            msg = "\n\n --- share  " + str(i) + ": " + str(s)
            #logger.debug(msg)
            i = i + int(1)

            thisid = -1 * (int(s['id']))
            msg = "       -- thisid: " + str(thisid)
            #logger.debug(msg)
            nfsexport_exists = False
            try:
                if thisid in existing_exports:
                    nfsexport_exists = True
            except:
                pass
            if thisid < 0:
                try:
                    msg = "   thisid < 0 " + str(nfsexport_exists) + " for thisid " + str(thisid)
                    # logger.debug(msg)
                    thisid = -1 * thisid
                    if thisid in existing_exports:
                        nfsexport_exists = True
                except:
                    nfsexport_exists = False

            msg = "   nfsexport_exists is " + str(nfsexport_exists) + " for thisid " + str(thisid)
            #logger.debug(msg)

            thisfspath = str(s['fs_path'])
            thisfspath = thisfspath.replace('\n', '')

            thisexportpath = str(s['export_path'])
            thisexportpath = thisexportpath.replace('\n', '')
            msg = "       -- thisexportpath is " + str(thisexportpath)
            #logger.debug(msg)

            description = str(s['description'])
            if description == '':
                description = thisexportpath

            msg = "        -- description is " + str(description)
            #logger.debug(msg)

            thisrestrictions = []
            myrestrictions = []
            export_in_myshares = 0
            for ms in myshares:
                if ms['export_path'] == thisexportpath:
                    export_in_myshares = int(ms['id'])
                    for hr in ms['restrictions']:
                        myrestrictions.append(hr['host_restrictions'])
                    msg = "   export_in_myshares " + str(export_in_myshares) + " ... breaking\n"
                    #logger.debug(msg)
                    break

            if nfsexport_exists:
                need_to_update = False
                msg = "     found thisid " + str(thisid) + " in existing_exports"
                #logger.debug(msg)
                nfssearch = NfsExport.objects.filter(exportid=thisid, exportpath=thisexportpath)
                # If objects do not exist, we must create them
                if nfssearch.count() != 1:
                    msg = "  could not find NfsExport exportid = " + str(thisid) + " for exportpath " + str(
                        thisexportpath)
                    logger.info(msg)
                    sys.exit(-1)
                else:
                    nfssearch = nfssearch[0]

                cpathdirid = nfssearch.clusterpath.dirid
                cpath = Clusterpath.objects.filter(dirid=cpathdirid, cluster_id=self.id)
                thisclusterpath = cpath[0]
                # msg = "    thisclusterpath is " + str(thisclusterpath)
                #logger.debug(msg)
                if thisclusterpath.get_id() == thisid:
                    if thisclusterpath.get_dirpath() != thisexportpath:
                        thisclusterpath.set_dirpath(thisexportpath)
                        thisclusterpath.save()
                        need_to_update = True
                        msg = "     dirpath " + str(thisclusterpath.get_dirpath()) + "!= thisexportpath " + str(
                            thisexportpath)
                        #logger.debug(msg)

                if nfssearch.exportpath != thisexportpath:
                    nfssearch.exportpath = thisexportpath
                    need_to_update = True
                    msg = "     nfssearch.exportpath " + str(nfssearch.exportpath) + "!= thisexportpath " + str(
                        thisexportpath)
                    #logger.debug(msg)

                if nfssearch.description != description:
                    nfssearch.description = description
                    need_to_update = True
                    msg = "     nfssearch.description " + str(nfssearch.description) + "!= thisexportpath " + str(
                        thisexportpath)
                    #logger.debug(msg)

                nfsrestrictions = nfssearch.restrictions.all()
                msg = "   A nfsrestrictions: " + str(nfsrestrictions)
                #logger.debug(msg)
                theseips = []
                allnewr = []
                allr = Restriction.objects.all()
                msg = "   A allr: " + str(allr)
                #logger.debug(msg)
                for nfsr in nfsrestrictions:
                    msg = "    nfsr.name = " + str(nfsr.name)
                    # logger.debug(msg)
                    keep = set()
                    foundexact = False
                    for r in allr:
                        msg = "      r.name = " + str(r.name)
                        # logger.debug(msg)
                        if str(nfsr.name) == "/":
                            if str(nfsr.name) == str(r.name):
                                keep.add(r.name)
                                foundexact = True
                                break
                        else:
                            if re.match(str(nfsr.name), str(r.name)):
                                keep.add(r.name)
                                foundexact = True
                                break
                            else:
                                pattern = "^" + str(nfsr.name)
                                if re.match(pattern, str(r.name)):
                                    keep.add(r.name)
                    msg = "   keep is " + str(keep) + " for nfsr.name: " + str(nfsr.name)
                    # logger.debug(msg)
                    newkeep = set()
                    if foundexact is True:
                        for r in keep:
                            if re.match(str(nfsr.name), str(r)):
                                newkeep.add(r)
                    else:
                        for r in keep:
                            if re.match(settings.MZpattern, str(r)):
                                newkeep.add(r)
                    keep = newkeep
                    msg = "     keep is now " + str(keep) + " for nfsr " + str(nfsr.name)
                    # logger.debug(msg)

                    qs = Restriction.objects.filter(name__in=keep)
                    if qs.count() < 1:
                        msg = "  A could not find Restriction(s) " + str(nfsr.name) + " ---- sys.exit(-1)"
                        logger.critical(msg)
                        sys.exit(-1)
                    else:
                        msg = "    found " + str(int(qs.count())) + " Restrictions for " + str(nfsr.name)
                        # logger.debug(msg)

                    # loop through the relevant restrictions
                    allnewr = []
                    for nr in qs:
                        msg = "    nr = " + str(nr)
                        #logger.debug(msg)

                        for rn in range(0, len(s['restrictions'])):
                            r = s['restrictions'][rn]
                            rupdated = False
                            thisumapid = int(r['map_to_user_id'])
                            if int(nr.usermapid) != thisumapid:
                                msg = "    if nfsr.usermapid = int(" + str(nfsr.usermapid) + " != thisumapid " + str(
                                    thisumapid)
                                #logger.debug(msg)
                                nr.usermapid = thisumapid
                                rupdated = True

                            thisumapping = str(r['user_mapping'])
                            thisumapping = thisumapping.replace("u'", "")
                            thisumapping = convert_nfs_user_mapping(thisumapping)
                            if nr.usermapping != thisumapping:
                                msg = "    if nfsr.usermapping = " + str(
                                    nfsr.usermapping) + " != UM_CHOICES[thisusermapping] " + str(thisumapping)
                                #logger.debug(msg)
                                nr.usermapping = thisumapping
                                rupdated = True

                            thisreadonly = int(r['read_only'])
                            if int(nr.readonly) != thisreadonly:
                                msg = "    if nfsr.readonly = int(" + str(
                                    int(nfsr.readonly)) + ") != thisreadonly " + str(
                                    thisreadonly)
                                #logger.debug(msg)
                                nr.readonly = thisreadonly
                                rupdated = True

                            newr = r['host_restrictions']
                            newr.sort()
                            allnewr.append(newr)
                            nfsrips = nr.get_all_ipzone_ipaddrs()
                            if nfsrips != newr:
                                msg = "    nfsrips " + str(nfsrips) + " != newr " + str(newr)
                                #logger.debug(msg)
                                nr.set_default_ipzone_ipaddrs(newr)
                                rupdated = True

                        if rupdated is True:
                            nr.usermapid = thisumapid
                            nr.usermapping = thisumapping
                            nr.readonly = thisreadonly
                            for ip in newr:
                                theseips.append(ip)
                            updated.append('nfsrestriction ' + str(nr))

                allnewr.sort()
                myrestrictions.sort()
                if allnewr != myrestrictions:
                    msg = "   allnewr != myrestrictions " + str(allnewr) + "\n" + str(myrestrictions) + "\n"
                    #logger.debug(msg)
                    need_to_update = True

                if need_to_update is True:
                    nfssearch.save()
                    nfssearch.set_organization(thisclusterpath.organization)
                    nfsrestrictions = nfssearch.restrictions.all()
                    msg = "   B nfsrestrictions: " + str(nfsrestrictions) + " for nfssearch " + str(nfssearch)
                    # logger.debug(msg)
                    allr = Restriction.objects.all()
                    # msg = "   B allr: " + str(allr) + "\n"
                    # logger.debug(msg)
                    keep = set()
                    foundexact = False
                    for nfsr in nfsrestrictions:
                        for r in allr:
                            msg = "   r is " + str(r) + " and nfsr.name is " + str(nfsr.name)
                            # logger.debug(msg)
                            if str(nfsr.name) == "/":
                                if str(nfsr.name) == str(r.name):
                                    keep.add(r.name)
                                    foundexact = True
                                    break
                            else:
                                if re.match(str(nfsr.name), str(r.name)):
                                    keep.add(r.name)
                                    foundexact = True
                                    break
                                else:
                                    pattern = "^" + str(nfsr.name)
                                    if re.match(pattern, str(r.name)):
                                        keep.add(r.name)
                            # msg = "    initial keep is " + str(keep)
                            # logger.debug(msg)

                        newkeep = set()
                        if foundexact is True:
                            for r in keep:
                                if re.match(str(nfsr.name), str(r)):
                                    newkeep.add(r)
                        else:
                            for r in keep:
                                if re.match(settings.MZpattern, str(r)):
                                    newkeep.add(r)
                        # msg = "   newkeep is " + str(newkeep) + " for nfsrestrictions: " + str(nfsrestrictions)
                        # logger.debug(msg)
                        for k in newkeep:
                            keep.add(k)

                    msg = "   keep is " + str(keep) + " for nfsrestrictions: " + str(nfsrestrictions)
                    #logger.debug(msg)
                    qs = Restriction.objects.filter(name__in=keep)
                    # msg = "    qs = " + str(qs)
                    # logger.debug(msg)
                    if qs.count() < 1:
                        msg = "       B could not find Restriction(s) in keep " + str(keep) + " for nfssearch " + str(
                            nfssearch)
                        # logger.debug(msg)
                        for r in allnewr:
                            msg = "    from allnewr adding r: " + str(r)
                            # logger.debug(msg)
                            nfssearch.restrictions.add(r)
                    else:
                        for r in qs:
                            msg = "   r is " + str(r)
                            # logger.debug(msg)
                            msg = "       theseips are: " + str(theseips)
                            #logger.debug(msg)
                            r.set_default_ipzone_ipaddrs(theseips)
                            nfssearch.restrictions.add(r)
                    nfssearch.save(update_on_cluster=True)
                    nfssearch.set_organization(thisclusterpath.organization)
                    updated.append('nfssearch ' + nfssearch.exportpath)
                else:
                    ok.append("nfsexport " + str(nfssearch.exportpath))
                #existing_exports.remove(thisid)

            #  thisid not in existing_exports
            else:
                # need to create a new export
                msg = "   need to create new export for thisid " + str(thisid)
                # logger.debug(msg)
                if export_in_myshares > 0:
                    thisid = export_in_myshares
                    msg = "     thisid set to export_in_myshares = " + str(thisid)
                    #logger.debug(msg)
                # msg = "     found " + str( len(s['restrictions']) )
                # logger.debug(msg)
                thisorgid = -1
                for rn in range(0, len(s['restrictions'])):
                    r = s['restrictions'][rn]
                    msg = "rn " + str(rn) + ": r = " + str(r)
                    #logger.debug(msg)
                    thisumapid = int(r['map_to_user_id'])
                    thisumapping = str(r['user_mapping'])
                    thisumapping = thisumapping.replace("u'", "")
                    thisumapping = convert_nfs_user_mapping(thisumapping)
                    thisreadonly = r['read_only']
                    ipaddrlist = r['host_restrictions']
                    msg = "ipaddrlist: " + str(ipaddrlist)
                    #logger.debug(msg)

                    # ASSUME the first entry in an export path is the organization
                    oname = str(thisexportpath).encode('ascii', 'ignore')
                    msg = " oname from thisexportpath is " + str(oname)
                    #logger.debug(msg)
                    if oname[0:1] == '/':
                        oname = oname.split('/')
                        msg = "    split oname is : " + str(oname)
                        #logger.debug(msg)
                        oname = oname[1]
                        if len(oname) < 2:
                            # make '/' owned by its
                            now = datetime.datetime.utcnow()
                            msg = str(now) + ":changedoname:" + str(oname) + "_to_its" + ":" + creator_msg
                            logger.info(msg)
                            oname = 'its'

                    if oname == 'data':
                        # make it owned by its
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":changedoname:" + str(oname) + "_to_its" + ":" + creator_msg
                        logger.info(msg)
                        oname = 'its'

                    oname = oname.replace(" ", "_", 100)
                    msg = "  oname is " + str(oname) + " for thisexportpath = " + str(thisexportpath)
                    #logger.debug(msg)

                    qr = Organization.objects.filter(name=oname)
                    need_to_set_cps = False
                    if qr.count() == 0:
                        # If this export's organization does not exist, then assign it to 'ITS'
                        thisorg = Organization(name=oname)
                        thisorg.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addOrganization:" + str(oname) + ":" + creator_msg
                        logger.info(msg)
                        need_to_set_cps = True
                    else:
                        thisorg = qr[0]
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":foundOrganization:" + str(oname) + ":" + creator_msg
                        #logger.info(msg)

                    # default units in setttings are tb
                    try:
                        quotasize = settings.ORGANIZATION_QUOTA_LIMITS[str(oname)]
                        # special cases
                        if thisexportpath == '/' or thisexportpath == settings.QUMULO_BASE_PATH:
                            quotasize = settings.DEFAULT_CLUSTER_QUOTA_LIMIT
                    except:
                        quotasize = settings.ORGANIZATION_QUOTA_LIMITS['default']

                    qname = thisfspath + "/"
                    if qname[0:1] != "/":
                        qname = "/" + qname
                    qname = qname.replace("//", "/")
                    mgs = "      qname is " + str(qname)
                    #logger.debug(qname)

                    msg = " searching for Quota with qid = " + str(thisid) + " and organization = " + str(
                        thisorg) + "  --- qname is " + str(qname)
                    #logger.debug(msg)
                    qr = Quota.objects.filter(qid=thisid, organization=thisorg)
                    if qr.count() == 0:
                        msg = "  not found .... searching for Quota with qname = " + str(
                            qname) + " and organization " + str(thisorg) + "  --- thisid is " + str(thisid)
                        #logger.debug(msg)
                        qr = Quota.objects.filter(name=qname)
                        if qr.count() == 0:
                            msg = "   no quota for qname = " + str(qname)
                            #logger.debug(msg)
                            qr = Quota.objects.filter(name=settings.NONE_NAME)
                            if qr.count() != 1:
                                thisquota = Quota(name=settings.NONE_NAME)
                                thisquota.save()
                                now = datetime.datetime.utcnow()
                                msg = str(now) + ":addQuota:" + str(thisquota.name) + ":" + creator_msg
                                logger.info(msg)
                    thisquota = qr[0]

                    msg = "  found quota " + str(thisquota) + " for thisid = " + str(thisid)
                    #logger.debug(msg)

                    try:
                        fileattrs = fs.get_file_attr(conninfo, creds, thisfspath)
                        cpid = int(fileattrs.lookup('id'))
                    except qumulo.lib.request.RequestError as err:
                        msg = "         RequestError: " + str(err) + " at get_file_attr for thisfspath >" + str(
                            thisfspath) + "<"
                        # logger.debug(msg)
                        cpid = 0
                    msg = "   cpid = " + str(cpid) + " for thisfspath " + str(thisfspath)
                    # logger.debug(msg)

                    # if thisorg.name == 'its' or thisorg.name == 'data':
                    #    delete_state = True
                    # else:
                    #    delete_state = False
                    delete_state = False

                    thisqusage = settings.NONE_NAME
                    quotaname = str(thisquota.name).strip().encode('ascii', 'ignore')
                    if settings.NONE_NAME != quotaname:
                        thisqusage = QuotaUsage(size=quotasize, usage=int(0), quota=thisquota)
                        thisqusage.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addQuotaUsage:" + str(thisquota.name) + ":" + creator_msg
                        logger.info(msg)

                        cpid = self.create_directory_on_cluster(conninfo, creds, thisfspath)
                        qr = Clusterpath.objects.filter(dirid=cpid, cluster_id=self.id)

                        now = datetime.datetime.utcnow()
                        if qr.count() == 0:
                            thiscp = Clusterpath(dirid=cpid, dirpath=qname, quota=thisquota, cluster=self,
                                                 do_not_delete=delete_state, creator=creator_msg)
                            thiscp.save(create_on_cluster=True)
                            msg = str(now) + ":addClusterpath_qname:" + str(qname) + ":" + creator_msg
                            logger.info(msg)
                        else:
                            thiscp = qr[0]
                            msg = str(now) + ":foundClusterpath_cpid:" + str(cpid) + ":" + creator_msg
                            #logger.info(msg)
                    else:
                        qr = Clusterpath.objects.filter(dirid=cpid, dirpath=qname, cluster_id=self.id)
                        msg = "   qr.count = " + str(qr.count()) + " for cpid = " + str(cpid) + " and dirpath = " + str(
                            qname) + " and cluster " + str(self.id)
                        # logger.debug(msg)

                        now = datetime.datetime.utcnow()
                        if qr.count() == 0:
                            thiscp = Clusterpath(dirid=cpid, dirpath=qname, quota=thisquota, cluster=self,
                                                 do_not_delete=delete_state,
                                                 creator=creator_msg)
                            thiscp.save()
                            msg = str(now) + ":addClusterpath_cpid_qname:" + str(cpid) + "_" + str(
                                qname) + ":" + creator_msg
                            logger.info(msg)
                        else:
                            thiscp = qr[0]
                            msg = str(now) + ":foundClusterpath_cpid_qname:" + str(cpid) + "_" + str(
                                qname) + ":" + creator_msg
                            #logger.info(msg)

                    thisclusterpath = thiscp
                    msg = "   thiscp is " + str(thiscp)
                    #logger.debug(msg)

                    if need_to_set_cps == True:
                        thisorg.set_clusterpaths([thiscp])

                    # add this clusterpath to the organization and vice verse
                    thisorg.clusterpaths.add(thiscp)
                    thiscp.set_organization(thisorg)

                    # set the primary email address based on the organization
                    addr = email_from_orgname(thisorg.name)
                    thisquota.set_primary_email(addr)

                    # set the admin host list
                    try:
                        adminhostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS[str(thisorg)]
                    except:
                        adminhostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS['default']
                    thisorg.set_adminhosts(adminhostlist)

                    if thisqusage != settings.NONE_NAME:
                        thisqusage.set_organization(thisorg)

                    ipzoneinfo = get_zoneinfo_from_iplist(thisexportpath, ipaddrlist)
                    rname = thisexportpath

                    ipzs = []
                    for ipzmarker in ipzoneinfo.keys():
                        ipzname = ipzoneinfo[ipzmarker]['name']
                        if len(s['restrictions']) > 1:
                            thisrn = int(rn) + 1
                            ipzname = thisexportpath + "_" + str(thisreadonly) + "_" + str(
                                    thisumapping) + "_" + str(
                                    thisumapid) + settings.MZpattern + str(thisrn)
                            rname = ipzname

                        # make this IP zone immutable if it belongs to ITS or DATA
                        # if delete_state is True:
                        #    ipzname = 'immutable' + ipzname

                        qr = IPzone.objects.filter(name=ipzname)
                        if qr.count() == 0:
                            thisipz = IPzone(name=ipzname, organization=thisorg, creator=creator_msg)
                            # must save the IPzone before we can call set_ipaddrs method (which also calls save)
                            thisipz.save()
                            thisipz.set_ipzone_marker()
                            thisipzmarker = thisipz.get_ipzone_marker()
                            thisipzmarker = str(thisipzmarker).strip().encode('ascii', 'ignore')
                            ipaddrlist.append(thisipzmarker)
                            now = datetime.datetime.utcnow()
                            msg = str(now) + ":addIPzone:" + str(thisipz.name) + ":" + creator_msg + ":" + str(
                                thisipzmarker)
                            logger.info(msg)
                        else:
                            thisipz = qr[0]
                            thisipzmarker = thisipz.get_ipzone_marker()
                            thisipzmarker = str(thisipzmarker).strip().encode('ascii', 'ignore')

                        try:
                            test = ipzoneinfo[thisipzmarker]
                        except:
                            ipzoneinfo[thisipzmarker] = {}
                            ipzoneinfo[thisipzmarker]['name'] = ipzname
                            ipzoneinfo[thisipzmarker]['ipaddrs'] = ipzoneinfo[ipzmarker]['ipaddrs']

                        ipzs.append(thisipz)
                        msg = "    ipaddrlist is " + str(ipzoneinfo[ipzmarker]['ipaddrs']) + " for " + str(
                            ipzoneinfo[ipzmarker]['name'])
                        # logger.debug(msg)

                        thisipz.set_ipaddrs(ipzoneinfo[ipzmarker]['ipaddrs'])
                        if delete_state is True:
                            thisipz.set_immutable(True)

                        # add this IPzone to the organization
                        zones = thisorg.get_ipzones()
                        zones.append(thisipz)
                        thisorg.set_ipzones(zones)

                        #rname = ipzname
                        qr = Restriction.objects.filter(name=rname)
                        if qr.count() == 0:
                            newr = Restriction(name=rname, usermapid=thisumapid, usermapping=thisumapping,
                                               readonly=thisreadonly, do_not_delete=delete_state, creator=creator_msg)
                            newr.save()
                            newr.set_organization(thisorg)
                            now = datetime.datetime.utcnow()
                            msg = str(now) + ":addRestriction:" + str(newr.name) + ":" + creator_msg
                            logger.info(msg)
                        else:
                            newr = qr[0]

                        for ipz in ipzs:
                            newr.ipzones.add(ipz)
                        thisrestrictions.append(newr)
                        added.append('restriction' + newr.name)

                msg = "    thisrestrictions: " + str(thisrestrictions)
                #logger.debug(msg)

                # since its was imported, this exports's clusterpath is a root clusterpath
                newnfsx = NfsExport(exportid=thisid, clusterpath=thisclusterpath,
                                    exportpath=thisexportpath, description=description, create_subdirs=False,
                                    do_not_delete=delete_state, creator=creator_msg)
                # cannot create items on the cluster before organization and restrictions have been set
                newnfsx.save()
                msg = '  nfsexport' + newnfsx.exportpath
                added.append(msg)
                existing_exports.append(int(thisid))
                now = datetime.datetime.utcnow()
                msg = str(now) + ":addNFSExport:" + str(newnfsx.exportpath) + "_" + str(thisid) + ":" + creator_msg
                logger.info(msg)
                newnfsx.set_organization(thisorg)
                for tr in thisrestrictions:
                    newnfsx.restrictions.add(tr)

                # now we can create items on the cluster
                allr = newnfsx.restrictions.get_queryset()
                msg = "   allrestrictions are: " + str(allr)
                # logger.debug(msg)
                now = datetime.datetime.utcnow()
                msg = str(now) + ":newNFSexport:" + str(newnfsx.exportpath) + ":" + creator_msg
                if nfsexport_exists is True:
                    newnfsx.save(create_on_cluster=False)
                    msg = msg + ":coc_is_False"
                else:
                    newnfsx.save(create_on_cluster=True)
                    msg = msg + ":coc_is_True"
                logger.info(msg)

            if nfsexport_exists is True:
                existing_exports.remove(thisid)

        return activity


    def add_nfsexports_from_file(self, exports_filename):
        '''
        parses the given file of exports information and creates NfsEsxport objects
        '''

        added = []
        updated = []
        out_of_sync = []
        ok = []
        activity = {'added': added, 'updated': updated, 'out_of_sync': out_of_sync, 'ok': ok}

        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + "  ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        id = int(0)
        for line in fileinput.input(exports_filename):
            id = id - int(1)
            if "email::" in line:
                email = line.split("email::")
                email = email[1]
                msg = "  email: " + str(email)
                #logger.debug(msg)
            else:
                (limit, description, export_path) = line.split('\t')
                # msg = "    limit: " + str(limit)
                # logger.debug(msg)
                # msg = "     desc: " + str(description)
                # logger.debug(msg)
                if export_path != "/":
                    fspath = settings.QUMULO_BASE_PATH + "/" + export_path
                else:
                    fspath = export_path
                fspath = str(fspath).strip('\n')
                # msg = "   fspath: " + str(fspath)
                # logger.debug(msg)
                qname = id
                qr = Quota.objects.filter(qid=id)
                if qr.count() == 0:
                    rquota = Quota(qid=id, name=qname)
                    rquota.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":Quota:" + str(rquota.name) + ":add_from_file"
                    logger.info(msg)
                    rquota.set_pctusage()
                else:
                    rquota = qr[0]
                try:
                    fileattrs = fs.get_file_attr(conninfo, creds, fspath)
                    cpid = int(fileattrs.lookup('id'))
                    msg = "   cpid = " + str(cpid) + " for fspath " + str(fspath)
                    #logger.debug(msg)
                except qumulo.lib.request.RequestError as err:
                    msg = "         RequestError: " + str(err) + " at get_file_attr for fspath >" + str(
                        fspath) + "<"
                    #logger.debug(msg)
                    cpid = id

                msg = "   cpid = " + str(cpid)
                #logger.debug(msg)
                qr = Clusterpath.objects.filter(dirid=cpid, cluster_id=self.id)
                msg = "   qr.count = " + str(qr.count()) + " for cpid = " + str(cpid)
                #logger.debug(msg)

                if qr.count() == 0:
                    thiscp = Clusterpath(dirid=cpid, dirpath=fspath, quota=rquota, cluster=self)
                    thiscp.save(create_on_cluster=True)
                    #thiscp.save()

                else:
                    thiscp = qr[0]
                thisclusterpath = thiscp

                oname = export_path.split('/')
                oname = oname[0]
                oname = oname.replace(" ", "_", 100)
                qr = Organization.objects.filter(name=oname)
                if qr.count() == 0:
                    thisorg = Organization(name=oname)
                    thisorg.save()
                    thisorg.set_clusterpaths([thiscp])
                    try:
                        hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS[str(thisorg)]
                    except:
                        hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS['default']
                    thisorg.set_adminhosts(hostlist)
                    ipaddrlist = hostlist
                else:
                    thisorg = qr[0]
                    ipaddrlist = thisorg.get_hosts()

                # rquota.set_organization(thisorg)
                thiscp.set_organization(thisorg)

                ipzname = oname
                qr = IPzone.objects.filter(name=ipzname)
                if qr.count() == 0:
                    thisipz = IPzone(name=ipzname, organization=thisorg)
                    thisipz.save()
                    thisipz.set_ipzone_marker()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":IPzone:" + str(thisipz.name) + ":add_from_file"
                    logger.info(msg)
                else:
                    thisipz = qr[0]
                # must save the IPzone before we can call set_ipaddrs method (which also calls save)
                thisipz.set_ipaddrs(ipaddrlist)

                rname = oname
                qr = Restriction.objects.filter(name=rname)
                if qr.count() == 0:
                    newr = Restriction(name=rname, usermapid=0, usermapping='NFS_MAP_NONE',
                                       readonly='False')
                    newr.save()
                    newr.ipzone.add(thisipz)
                    newr.save
                    newr.set_organization(thisorg)
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":Restriction:" + str(newnfsx.exportpath) + ":add_from_file"
                    logger.info(msg)
                else:
                    newr = qr[0]
                thisrestrictions = []
                thisrestrictions.append(newr)
                added.append('restriction' + newr.name)

                newnfsx = NfsExport(exportid=id, clusterpath=thisclusterpath, exportpath=export_path)
                newnfsx.save()
                added.append('nfsexport' + newnfsx.name)
                # cannot add restrictions before first saving the export
                newnfsx.set_restrictions(thisrestrictions)
                newnfsx.set_organization(thisclusterpath.organization)
                newnfsx.save(create_on_cluster=True)

                now = datetime.datetime.utcnow()
                msg = str(now) + ":NFSExport:" + str(newnfsx.exportpath) + ":add_from_file"
                logger.info(msg)
        return activity

    def host_restrictions_to_ipaddrlist(self, hr):
        ilist = []
        hr = str(hr)
        # print( "    in host_restrictions_to_ipaddrlist -- hr = " + str(hr) )
        # if hr == '':
        #    all hosts are permitted (by qumulo)
        # pass
        if "," in hr:
            # comma delimited list of hosts
            # print("  hr is comma delimited list of hosts")
            for h in hr.split(', '):
                h = h.replace("u'", "'")
                h = h.replace("[", "")
                h = h.replace("]", "")
                h = h.replace("'", "", 10000)
                # print("                            h = " + h )
                ilist.append(str(h))

        if "/" in hr or "-" in hr:
            # network segment
            hr = hr.replace("u'", "'", 10000)
            hr = hr.replace("[", "")
            hr = hr.replace("]", "")
            hr = hr.replace("'", "", 10000)
            if "/" in hr:
                ipv4 = IPv4Network(hr)
                for host in ipv4.iterhosts():
                    ilist.append(str(host))

            if "-" in hr:
                '''  from qumulo nfsexports screen --  IP range: 192.168.1.1-192.168.1.10 or 192.168.1.1-10 '''
                ips = str(hr).split('-')
                prefix = ips[0].split('.')
                prefix = str(prefix[0]) + '.' + str(prefix[1]) + '.' + str(prefix[2])
                if not '.' in ips[1]:
                    count = ips[1]
                else:
                    ips = ips[0].split('.')
                    count = ips[3]
                    prefix2 = str(ips[0]) + '.' + str(ips[1]) + '.' + str(ips[2])
                    if prefix2 != prefix:
                        msg = "prefix mismatch for " + str(ips) + " pf1: " + str(prefix) + ",  pf2: " + str(prefix2)
                        #logger.debug(msg)
                for i in range(0, int(count)):
                    host = prefix + '.' + str(i)
                    ilist.append(host)
        return ilist

    def remove_all_cluster_items(self):
        '''
        removes ALL shares (quotas) and nfsexports found on the cluster
        :return:
        '''
        files = []
        shares = []
        nfsexports = []
        activity = {'files': files, 'shares': shares, 'nfsexports': nfsexports}

        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + "  ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        shares = self.fetch_nfs_shares(self)
        #logger.debug("     shares: " + str(shares) + "\n")

        msg = ""
        dmsg = ""
        for s in shares:
            dmsg = self.delete_nfsexport_on_cluster(conninfo, creds, xid=int(s['id']))
            msg = dmsg + "\n" + msg
        #logger.debug(msg)

        qclusterpaths = self.fetch_qumulo_shares(self)
        #logger.debug("     qclusterpaths: " + str(qclusterpaths) + "\n")

        msg = ''
        for qcp in qclusterpaths:
            dmsg = self.delete_quota_on_cluster(conninfo, creds, id=qcp['id'], path=qcp['path'])
            msg = dmsg + "\n" + msg
        # logger.debug(msg)

        shares = self.fetch_nfs_shares(self)
        qclusterpaths = self.fetch_qumulo_shares(self)
        msg = "remaining shares: " + str(len(shares)) + ", qcs:" + str(len(qclusterpaths))
        return msg

    def check_all_quotas(self):
        """
        checks all quota usages of all clusterpaths --- check_usage sends email as needed
        :return:
        """
        allcps = Clusterpath.objects.filter(cluster=self)
        for cp in allcps:
            msg = " checking quota: " + str(cp.quota)
            # logger.debug(msg)
            if cp.quota.qid > 0:
                cp.quota.check_usage()
            # else:
            #    msg = "    skipping cp.quota " + str(cp.quota)
            #    logger.debug(msg)


    def get_current_activity(self):
        """
        stores all the current sampled IOPS and activity (by host)
        """
        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + "  ... exiting"
            logger.critical(msg)
            sys.exit(-1)
        startdt = datetime.datetime.utcnow()
        startdt = startdt.replace(tzinfo=pytz.UTC)
        startutc = startdt.strftime('%s')
        sample = qumulo.rest.analytics.current_activity_get(conninfo=conninfo, credentials=creds)
        endfetch = datetime.datetime.utcnow().strftime('%s')
        fetch_duration = int(endfetch) - int(startutc)
        numsamples = len(sample.data['entries'])
        msg = " fetched " + str(numsamples) + " samples in " + str(fetch_duration) + " seconds"
        logger.info(msg)
        print(msg)
        self.load_activity_sample(conninfo=conninfo, creds=creds, sample=sample, validtime=startdt)

    def load_activity_sample(self, conninfo, creds, sample, validtime):
        startutc = datetime.datetime.utcnow()
        startutc = startutc.strftime('%s')
        endfetch = datetime.datetime.utcnow().strftime('%s')
        fetch_duration = int(endfetch) - int(startutc)
        hostinfo = {}
        types = set()
        i = int(1)
        for e in sample.data['entries']:
            # if i % 100 == int(0):
            #    print( str(i) + " of " + str(numsamples) )
            #i = i + int(1)

            type = ''
            for (k, v) in ACTIVITY_CHOICES:
                if v == e['type']:
                    type = k
                    break
            types.add(k)

            ip = str(e['ip']).strip().encode('ascii', 'ignore')
            rate = float(e['rate'])
            try:
                test = hostinfo[ip]
            except:
                hostinfo[ip] = {}
            try:
                test = hostinfo[ip][type]
                hostinfo[ip][type]['rawrates'].append(rate)
            except:
                hostinfo[ip][type] = {}
                hostinfo[ip][type]['rawrates'] = []
                hostinfo[ip][type]['rawrates'].append(rate)
                hostinfo[ip][type]['fileids'] = set()
            hostinfo[ip][type]['fileids'].add(int(e['id']))

        noneipz = IPzone.objects.filter(name=settings.NONE_NAME)
        if noneipz.count() < 1:
            msg = "cannot find IPzone " + str(settings.NONE_NAME)
            logger.critical(msg)
            sys.exit(-1)
        else:
            noneipz = noneipz[0]

        noneorg = Organization.objects.filter(name=settings.NONE_NAME)
        if noneorg.count() < 1:
            msg = "cannot find Organization " + str(settings.NONE_NAME)
            logger.critical(msg)
            sys.exit(-1)
        else:
            noneorg = noneorg[0]

        totalsamples = int(0)
        numactivities = int(0)
        numhosts = len(hostinfo.keys())
        # print( "found " + str(numhosts) + " hosts")
        idsseen = []
        for ip in hostinfo.keys():
            qr = Host.objects.filter(ipaddr=ip)
            now = datetime.datetime.utcnow()
            if qr.count() == 0:
                host = Host(ipaddr=ip, ipzone=noneipz, organization=noneorg)
                host.save()
                host.check_hostname()
                hostip = str(host) + "_as_" + str(ip)
                msg = str(now) + ":addHostbyip:" + str(hostip) + ":get_current_activity"
                logger.info(msg)
            else:
                host = qr[0]
                hostip = str(host) + "_as_" + str(ip)
                msg = str(now) + ":foundHostbyip:" + str(hostip) + ":get_current_activity"
                logger.info(msg)

            for t in types:
                # print( str(ip) + ":" + str(t) )
                acttype = ActivityType.objects.filter(id=t)
                if acttype.count() == 1:
                    acttype = acttype[0]
                else:
                    msg = " cannot file ActivityType for t " + str(t)
                    logger.critical(msg)
                    sys.exit(-1)
                paths = set()
                try:
                    test = hostinfo[ip][t]
                except:
                    # print( "key error for ip " + str(ip) + " and t " + str(t))
                    continue

                for id in hostinfo[ip][t]['fileids']:
                    if str(id) in str(idsseen):
                        continue
                    try:
                        rr = qumulo.rest.fs.get_file_attr(conninfo=conninfo, credentials=creds, id_=id)
                        paths.add(rr.lookup('path'))
                        msg = "      paths: " + str(paths)
                        # print(paths)
                    except qumulo.lib.request.RequestError as err:
                        pass
                        # msg = "         RequestError: " + str(err) + " at get_file_attr for id " + str(id)
                        # print(msg)
                    idsseen.append(id)

                tl = []
                for p in paths:
                    tl.append(p)
                if len(tl) > 1:
                    tl.sort()
                    # no need to add keep the base path in every record
                    basefilepath = str(tl[0])
                    basefilepath = basefilepath.replace(settings.QUMULO_BASE_PATH, "")
                else:
                    basefilepath = 'notfound'

                try:
                    mean = avg_calc(hostinfo[ip][t]['rawrates'])
                    std = sd_calc(hostinfo[ip][t]['rawrates'])
                    numsamples = len(hostinfo[ip][t]['rawrates'])
                    rawrates = str()
                    for r in hostinfo[ip][t]['rawrates']:
                        rawrates = rawrates + ", " + str(r)
                    rawrates = re.sub(", $", "", rawrates)
                    rawrates = re.sub("^, ", "", rawrates)
                    act = Activity(activitytype=acttype, host=host, mean=mean, std=std, numsamples=numsamples,
                                   basefilepath=basefilepath, rawrates=rawrates, validtime=validtime)
                    act.save()
                    numactivities = numactivities + int(1)
                    totalsamples = totalsamples + numsamples
                except:
                    # May not have all types for a given host in a sample
                    pass
        endsave = datetime.datetime.utcnow().strftime('%s')

        storage_duration = int(endsave) - int(endfetch)
        af = ActivityFetch(beginfetch=startutc, numsamples=totalsamples, numactivities=numactivities,
                           fetch_duration=fetch_duration, storage_duration=storage_duration, numhosts=numhosts)
        af.save()
        msg = " ... stored " + str(numactivities) + " activities for " + str(numhosts) + " hosts from " + str(
            totalsamples) + " samples in " + str(storage_duration) + " seconds"
        print(msg)

    def get_slot_status(self):
        """
        stores all current slot status info

        :return:
        """
        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + "  ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        slots = qumulo.rest.cluster.get_cluster_slots_status(conninfo=conninfo, credentials=creds)
        for s in slots.data:
            snum = s['slot']
            capacity = s['capacity']
            diskmodel = s['disk_model']
            disktype = s['disk_type']
            slottype = s['slot_type']
            state = str(s['state'])
            nodeid = s['node_id']
            qid = str(s['id'])

            now = datetime.datetime.utcnow()
            msg = str(now)
            qs = ClusterSlot.objects.filter(qid=qid)
            if qs.count() == 0:
                cs = ClusterSlot(slot=snum, capacity=capacity, disk_model=diskmodel, slot_type=slottype, state=state,
                                 node_id=nodeid, disk_type=disktype, qid=qid)
                msg = msg + ":addClusterSlot:" + str(cs.qid) + ":get_slot_status"
                cs.save()
                logger.info(msg)
            else:
                cs = qs[0]
                ntu = False
                if cs.slot != snum:
                    cs.slot = snum
                    ntu = True
                if cs.capacity != capacity:
                    cs.capacity = capacity
                    ntu = True
                if cs.disk_model != diskmodel:
                    cs.disk_model = diskmodel
                    ntu = True
                if cs.disk_type != disktype:
                    disk_type = disktype
                    ntu = True
                if cs.state != state:
                    cs.state = state
                    ntu = True
                if cs.node_id != nodeid:
                    cs.node_id = nodeid
                    ntu = True
                if ntu is True:
                    cs.save()
                    msg = msg + ":updatingClusterSlot:" + str(cs.qid) + ":get_slot_status"
                    logger.info(msg)

            if "Healthy" not in state:
                msg = msg + ":foundUnhealtyClusterSlot:" + str(qid) + ":get_slot_status"
                logger.info(msg)
                self.send_email_to_superusers(msg=msg)

    def send_email_to_superusers(self, msg):
        suset = set()
        qs = Sysadmin.objects.all()
        for sa in qs:
            if sa.is_a_superuser is True:
                suset.add(sa)
        msg = "suset: " + str(suset)
        logger.info(msg)

    def initialize_activitystats(self):
        names = []
        names.append(settings.HOST_STATISTICS_PREFIX + "All")
        qs = Organization.objects.all()
        for org in qs:
            names.append('x')

        for n in names:
            qs = Host.objects.filter(name=n)
            if qs.count == 0:
                pass

    def update_all_activitystats(self):
        host = Host.objects.first()
        validfrom = datetime.datetime.utcnow()
        validfrom = validfrom.replace(tzinfo=pytz.UTC)
        validto = datetime.datetime.utcnow()
        validto = validto.replace(tzinfo=pytz.UTC)
        validtime = validto - validfrom
        actstat = ActivityStat(activitytype=1, host=host, mean=1.0, std=3.0, numsamples=10, validfrom=validfrom,
                               validto=validto, validtime=validtime)
        actstat.save()
        pass

    def get_current_connections(self):
        """
        stores all the current connection information (by host and connection type)
        """
        (conninfo, creds) = qlogin(self.ipaddr, self.adminname, self.adminpassword, self.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.name) + "  ... exiting"
            logger.critical(msg)
            sys.exit(-1)
        startdt = datetime.datetime.utcnow()
        startdt = startdt.replace(tzinfo=pytz.UTC)
        startutc = startdt.strftime('%s')
        samples = qumulo.rest.network.connections(conninfo=conninfo, credentials=creds)
        endfetch = datetime.datetime.utcnow().strftime('%s')
        fetch_duration = int(endfetch) - int(startutc)
        numsamples = len(samples.data)
        msg = " fetched " + str(numsamples) + " samples in " + str(fetch_duration) + " seconds"
        logger.info(msg)
        print(msg)
        self.load_connections_sample(samples=samples.data, validtime=startdt, beginfetch=startutc,
                                     fetchduration=fetch_duration)

    def load_connections_sample(self, samples, validtime, beginfetch, fetchduration):
        startutc = datetime.datetime.utcnow()
        startutc = startutc.strftime('%s')
        endfetch = datetime.datetime.utcnow().strftime('%s')
        fetch_duration = int(endfetch) - int(startutc)
        hostinfo = {}
        types = set()
        i = int(1)
        for s in samples:
            nodeid = s['id']
            for c in s['connections']:
                ctype = str(c['type']).strip().encode('ascii', 'ignore')
                types.add(ctype)
                ip = str(c['network_address']).strip().encode('ascii', 'ignore')
                try:
                    test = hostinfo[ip]
                except:
                    hostinfo[ip] = {}
                try:
                    test = hostinfo[ip]['ctype']
                    hostinfo[ip]['numconnections'] = hostinfo[ip]['numconnections'] + int(1)
                except:
                    hostinfo[ip] = {}
                    hostinfo[ip]['ctype'] = ctype
                    hostinfo[ip]['numconnections'] = int(1)
                    hostinfo[ip]['nodeid'] = nodeid

        iplist = hostinfo.keys()
        iplist.sort()
        connections_per_host = {}
        for ip in iplist:
            qs = Host.objects.filter(ipaddr=ip)
            if qs.count() == 1:
                hostname = str(qs[0])
            else:
                hostname = str(ip)
            try:
                test = connections_per_host[hostname]
            except:
                connections_per_host[hostname] = {}
                connections_per_host[hostname]['hostname'] = hostname
                connections_per_host[hostname]['ctype'] = hostinfo[ip]['ctype']
                connections_per_host[hostname]['numconnections'] = hostinfo[ip]['numconnections']
                connections_per_host[hostname]['nodeid'] = hostinfo[ip]['nodeid']

        bynodeid = {}
        hostnames = connections_per_host.keys()
        hostnames.sort()
        for hostname in hostnames:
            qr = ConnectionType.objects.filter(name=connections_per_host[hostname]['ctype'])
            if qr.count() == 0:
                ctype = ConnectionType(name=connections_per_host[hostname]['ctype'])
                ctype.save()
            else:
                ctype = qr[0]

            nodeid = connections_per_host[hostname]['nodeid']
            try:
                test = bynodeid[nodeid]
            except:
                bynodeid[nodeid] = {}
                bynodeid[nodeid]['ctype'] = ctype
                bynodeid[nodeid]['cph'] = []
            cph = {}
            cph[connections_per_host[hostname]['hostname']] = connections_per_host[hostname]['numconnections']
            bynodeid[nodeid]['cph'].append(cph)

        number_of_connections = int(0)
        number_of_hosts = int(0)
        connections = []
        nodeids = bynodeid.keys()
        nodeids.sort()
        for nodeid in nodeids:
            by_num_connections = {}
            for entry in bynodeid[nodeid]['cph']:
                hostname = entry.keys()
                numconns = entry[hostname[0]]
                try:
                    test = by_num_connections[numconns]
                except:
                    by_num_connections[numconns] = []
                by_num_connections[numconns].append(hostname[0])

            nid = ClusterNode.objects.filter(id=nodeid)
            if nid.count() < 1:
                nid = ClusterNode(id=nodeid, name=str(nodeid))
                nid.save()
            else:
                nid = nid[0]

            qs = Connection.objects.filter(connectiontype=bynodeid[nodeid]['ctype'], nodeid=nid).order_by('id').last()
            if qs is None:
                connection = Connection(connectiontype=bynodeid[nodeid]['ctype'], nodeid=nid,
                                        connections_per_host=bynodeid[nodeid]['cph'],
                                        hosts_by_num_connections=by_num_connections, validtime=validtime)
                connection.save()
                connections.append(connection)
                count = int(0)
                for xd in bynodeid[nodeid]['cph']:
                    for k in xd.keys():
                        count = count + xd[k]
                number_of_connections = number_of_connections + count
                number_of_hosts = number_of_hosts + len(bynodeid[nodeid]['cph'])
            else:
                old_cph = {}
                data = qs.get_cbh()
                ale = ast.literal_eval(data)
                for xd in ale:
                    for k in xd.keys():
                        old_cph[k] = xd[k]

                new_cph = {}
                newdata = bynodeid[nodeid]['cph']
                for nd in newdata:
                    junk = nd
                    for k in nd.keys():
                        new_cph[k] = nd[k]

                if new_cph != old_cph:
                    connection = Connection(connectiontype=bynodeid[nodeid]['ctype'], nodeid=nid,
                                            connections_per_host=bynodeid[nodeid]['cph'],
                                            hosts_by_num_connections=by_num_connections, validtime=validtime)
                    connection.save()
                    connections.append(connection)
                    count = int(0)
                    for xd in bynodeid[nodeid]['cph']:
                        for k in xd.keys():
                            count = count + xd[k]
                    number_of_connections = number_of_connections + count
                    number_of_hosts = number_of_hosts + len(bynodeid[nodeid]['cph'])
                else:
                    msg = str(qs) + " is up to date "
                    logger.debug(msg)

        if number_of_hosts > 0 and number_of_connections > 0:
            endfetch = datetime.datetime.utcnow().strftime('%s')
            storage_duration = int(endfetch) - int(startutc)
            cf = ConnectionFetch(numhosts=number_of_hosts, numconnections=number_of_connections, beginfetch=beginfetch,
                                 fetch_duration=fetch_duration, storage_duration=storage_duration)
            cf.save()
            for c in connections:
                cf.connections.add(c)
            cf.save()


###################################
#     ___              _          #
#    / _ \ _   _  ___ | |_ __ _   #
#   | | | | | | |/ _ \| __/ _` |  #
#   | |_| | |_| | (_) | || (_| |  #
#    \__\_\\__,_|\___/ \__\__,_|  #
#                                 #
###################################

class Quota(models.Model):
    qid = models.BigIntegerField("QID", default=-1)
    name = models.CharField('Name', max_length=200, default=settings.DEFUALT_QUOTANAME,
                            help_text="Directory path on cluster ")
    size = models.FloatField("Size", default=0, help_text=settings.HELP_TEXT_QUOTA_SIZE)
    units = models.CharField('Size units:', max_length=6, choices=SIZE_CHOICES, default=settings.DEFAULT_LIMIT_UNITS)
    usage = models.BigIntegerField("Usage in bytes", default=0)
    pctusage = models.FloatField("Use Percentage", default=0.0)
    warnpct = models.IntegerField('Warning Percentage', default=75,
                                  help_text="A WARNING message will be sent when this quota's current use exceeds this percentage")
    # get_warn_delay uses 86400 secs/day
    warnfreq = models.IntegerField('Warning Frequency (days)', default=3,
                                   help_text="Delay until next quota warning message will be sent")
    lastwarn = models.BigIntegerField('Last warning notification (utcsecond)', default=0)
    criticalpct = models.IntegerField('Critical Percentage', default=90,
                                      help_text="A CRITICAL message will be sent when this quota's current use exceeds this percentage")
    # get_critical_delay uses 3600 secs/hour
    criticalfreq = models.IntegerField('Critical Frequency (hours)', default=24,
                                       help_text="Delay until next quota critical message will be sent")
    lastcritical = models.BigIntegerField('Last critical notification (utcsecond)', default=0)
    fullpct = models.IntegerField('Full Percentage', default=98,
                                  help_text=mark_safe(
                                      "A FULL message will be sent when this quota's current use exceeds this percentage<br>The 98% default allows for 2% growth before the actual cutoff of data writing occurs"))
    # get_full_delay uses 60 secs/min
    fullfreq = models.IntegerField('Full Frequency (minutes)', default=60, help_text=mark_safe(
        "Delay until next quota full message will be sent<br><b>NOTE:</b> Once a quota is TRULY full (at 100% -- so writes have stopped) AND if <b>Full Percentage</b> is less than 100, then <b>Full Frequency</b> will be divided by 10.  So hourly notifications will become 6 minute notifications!"))
    lastfull = models.BigIntegerField('Last full notification (utcsecond)', default=0)
    primary = models.EmailField("Primary Contact Email:",
                                default=settings.EMAIL_HOST_USER,
                                help_text="noreply -- means no one from your branch will receive alerts about this quota!  This can be an email group.")
    secondary = models.EmailField("Secondary Contact Email:", default=settings.QRBA_ADMIN_EMAIL,
                                  help_text='A secondary contact for your branch or QRBA administrator (default)')
    organization = models.ForeignKey('provision.Organization', null=True, related_name='org_by_quota',
                                     help_text=settings.HELP_TEXT_ORGANIZATION)
    updated = models.DateTimeField("Updated:", auto_now=True)
    updated_on_cluster = models.DateTimeField("Updated on cluster", default='0001-01-01 00:00:01Z')
    colorname = models.CharField(max_length=7, default='black')
    do_not_delete = models.BooleanField(default=False, help_text=settings.HELP_TEXT_DND)
    creator = models.CharField(default='unknown', max_length=200)
    updater = models.CharField(default='None', max_length=200)

    def __str__(self):
        return str(self.name)

    def get_do_not_delete(self):
        return self.do_not_delete

    def save(self, *args, **kwargs):
        msg = "    saving quota: " + str(self.name) + ", id = " + str(self.id) + ", qid " + str(
            self.qid) + " for organization " + str(self.organization) + " --- my id is " + str(self.id)
        # logger.debug(msg)

        # enforce trailing '/' in name
        if self.name[len(self.name) - 1:len(self.name)] != '/':
            self.name = self.name + "/"

        if self.updated_on_cluster is None:
            dt = datetime.datetime.strptime("00010101T000001", '%Y%m%dT%H%M%S')
            dt = dt.replace(tzinfo=pytz.UTC)
            self.updated_on_cluster = dt

        # update email message 'last*' fields since the user may have changed them
        #     moved this logic to QuotaAdmin.save_model()
        # now = datetime.datetime.utcnow()
        # nowutc = int(now.strftime('%s'))
        # self.lastwarn = nowutc + self.get_warn_delay()
        # self.lastcritial = nowutc + self.get_critical_delay()
        #self.lastfull = nowutc + self.get_full_delay()

        # insure color is set as expected
        self.colorname = 'black'
        pctusage = self.get_pctusage()
        if pctusage > float(float(self.get_warnpct()) / float(100)):
            self.colorname = "magenta"
        if pctusage > float(float(self.get_criticalpct()) / float(100)):
            self.colorname = "orange"
        if pctusage > float(float(self.get_fullpct()) / float(100)):
            self.colorname = "red"

        super(Quota, self).save(*args, **kwargs)
        # now = datetime.datetime.utcnow()
        # msg = str(now) + ":superQuota:" + str(self.name) + ":" + self.get_updater()
        #logger.info(msg)

        # update this object on the cluster if needed
        if self.name != settings.NONE_NAME:
            size_times_units = self.get_size()
            units = str(self.get_units())
            if units == "mb":
                size_times_units = size_times_units * settings.QUOTA_1MB
            if units == "gb":
                size_times_units = size_times_units * settings.QUOTA_1GB
            if units == "tb":
                size_times_units = size_times_units * settings.QUOTA_1TB
            if units == 'pb':
                size_times_units = size_times_units * settings.QUOTA_1PB

            size_times_units = int(size_times_units)
            cps = Clusterpath.objects.filter(organization=self.organization)
            for cp in cps:
                if cp.quota == self:
                    msg = "cp.quota = " + str(cp.quota)
                    # logger.debug(msg)
                    uoc = unicode_to_datetime(self.get_updated_on_cluster())
                    msg = "uoc = " + str(uoc) + " -- type is " + str(type(uoc))
                    # logger.debug(msg)
                    lastupdated = unicode_to_datetime(self.get_updated())
                    msg = "lastupdated = " + str(lastupdated) + " -- type is " + str(type(lastupdated))
                    # logger.debug(msg)
                    msg = "cp.quota = " + str(cp.quota) + " uoc = " + str(uoc) + ",   lastupdated = " + str(lastupdated)
                    # logger.info(msg)
                    if uoc < lastupdated:
                        (conninfo, creds) = qlogin(cp.cluster.ipaddr, cp.cluster.adminname, cp.cluster.adminpassword,
                                                   cp.cluster.port)
                        if not conninfo:
                            msg = "could not connect to cluster " + str(self.name) + "  ... exiting"
                            logger.info(msg)
                            logger.critical(msg)
                            sys.exit(-1)
                    else:
                        msg = "  uoc >= lastupdated"
                        # logger.info(msg)

                    if int(self.qid) < int(0):
                        msg = "    self.qid = " + str(self.qid)
                        logger.info(msg)
                        msg = cp.cluster.create_quota_on_cluster(conninfo, creds, cp.dirid, cp.dirpath,
                                                                 size_times_units)
                        logger.info(msg)
                        if 'RequestError' not in msg:
                            qid = msg.split('qid:')
                            self.qid = int(qid[1])
                            super(Quota, self).save(*args, **kwargs)
                        else:
                            # quota may exist from a previons creation and needs to be updated
                            msg = cp.cluster.update_quota_on_cluster(conninfo, creds, cp.dirid, cp.dirpath,
                                                                     size_times_units)
                            logger.info(msg)
                            if 'RequestError' not in msg:
                                qid = msg.split('qid:')
                                self.qid = int(qid[1])
                                super(Quota, self).save(*args, **kwargs)
                            else:
                                rmsg = msg
                                logger.critical(rmsg)
                    else:
                        msg = cp.cluster.update_quota_on_cluster(conninfo, creds, cp.dirid, cp.dirpath,
                                                                 size_times_units)
                        logger.info(msg)
                        msg = " self.qid > 0 == " + str(self.qid) + "   msg = " + msg
                        # logger.info(msg)
                        # project update time into the future -- updated is set by the system during save() and
                        # w/o the timedelta updated_on_cluster will always be slight ahead self.updated
                        # the 2 minute delta allows more than enough time for django to get the DB in sync
                        # remember -- DB updates can be asynchronous
                        # I tied using 30 seconds, but performance was problematic
                        dt = uoc + datetime.timedelta(minutes=2)
                        dt = dt.replace(tzinfo=pytz.UTC)
                        self.updated_on_cluster = dt
                        super(Quota, self).save(*args, **kwargs)
                        fetched_uoc = self.get_updated_on_cluster()
                        msg = "    fetched_uoc = " + str(fetched_uoc)
                        #logger.info(msg)


    def delete(self, using=None, keep_parents=False):
        now = datetime.datetime.utcnow()
        msg = str(now)
        if self.get_do_not_delete() is False:
            self.delete_from_cluster()
            super(Quota, self).delete(using=using, keep_parents=keep_parents)
            msg = msg + ":deletedQuota:"
        else:
            msg = msg + ":attempted_deleteQuota:"
        msg = msg + str(self.name) + ":" + self.get_updater()
        logger.info(msg)

    def delete_from_cluster(self):
        if self.get_do_not_delete() is False:
            for cp in Clusterpath.objects.all():
                now = datetime.datetime.utcnow()
                if cp.quota == self:
                    cp.delete()
                    msg = str(now) + ":deleteFromClusterQuota:" + str(self.name) + ":" + self.get_updater()
                    logger.info(msg)
        else:
            now = datetime.datetime.utcnow()
            msg = str(now) + ":attempted_deleteFromClusterQuota:" + str(self.name) + ":" + self.get_updater()
            logger.info(msg)

    def get_size(self):
        return self.size

    def set_size(self, newsize):
        self.size = newsize
        self.save()
        self.set_pctusage()

    def set_qid(self, qid):
        if self.qid < 0:
            self.qid = qid
            self.save()

    def set_units(self, units):
        self.units = units
        self.save()

    def get_creator(self):
        return str(self.creator)

    def get_updater(self):
        return str(self.updater)

    def set_updater(self, who):
        self.updater = who
        self.save()

    def get_usage(self):
        return self.usage

    def get_pctusage(self):
        return self.pctusage

    def get_updated(self):
        return self.updated

    def get_updated_on_cluster(self):
        return self.updated_on_cluster

    def get_qid(self):
        return self.qid

    def get_units(self):
        return self.units

    def get_colorname(self):
        return self.colorname

    def get_warnpct(self):
        return self.warnpct

    def get_criticalpct(self):
        return self.criticalpct

    def get_fullpct(self):
        return self.fullpct

    def get_warnfreq(self):
        return self.warnfreq

    def get_criticalfreq(self):
        return self.criticalfreq

    def get_fullfreq(self):
        return self.fullfreq

    def get_lastwarn(self):
        return int(self.lastwarn)

    def get_warn_delay(self):
        return (self.get_warnfreq() * 86400)

    def get_lastcritical(self):
        return int(self.lastcritical)

    def get_critical_delay(self):
        return (self.get_criticalfreq() * 3600)

    def get_lastfull(self):
        return int(self.lastfull)

    def get_full_delay(self):
        return (self.get_fullfreq() * 60)

    def set_usage(self, usage):
        self.usage = usage
        self.save()
        self.set_pctusage()

    def set_pctusage(self):
        size = float(self.get_size())
        units = str(self.get_units())
        size_times_units = self.get_size_times_units(size, units)
        if size_times_units != 0.0:
            self.pctusage = float(self.get_usage()) / float(size_times_units)
        else:
            self.pctusage = -1.0
        self.save()

    def set_lastwarn(self, lw):
        self.lastwarn = lw
        self.save()

    def set_lastcritical(self, lc):
        self.lastcritical = lc
        self.save()

    def set_lastfull(self, lf):
        self.lastfull = lf
        self.save()

    def set_colorname(self, c):
        self.colorname = c
        self.save()

    def set_primary_email(self, addr):
        self.primary = addr
        self.save()

    def get_size_times_units(self, size, units):
        size_times_units = 0
        if units == "mb":
            size_times_units = size * settings.QUOTA_1MB
        if units == "gb":
            size_times_units = size * settings.QUOTA_1GB
        if units == "tb":
            size_times_units = size * settings.QUOTA_1TB
        if units == 'pb':
            size_times_units = size * settings.QUOTA_1PB
        return size_times_units

    def check_usage(self):
        """
        checks this quota's usage and sends email if use percentage exceedes warning, critical, or full thresholds
        send email to each quota owner as needed -- limited by the associated '*lastwarn' value
        :return:
        """
        now = datetime.datetime.utcnow()
        nowutc = int(now.strftime('%s'))
        msg = "     in check_usage " + str(self)
        #logger.debug(msg)

        # check warning limit  (frequency in days)
        subject = "subject"
        body = "body"
        sendmsg = False
        pctusage = self.get_pctusage()
        pctu = 100.0 * float(self.get_pctusage())
        pctu = "{0:.1f}".format(pctu)
        eventtype = int(0)
        color = "black"
        next_email = 0

        cluster = ""
        mycps = set()
        for cp in Clusterpath.objects.all():
            if self == cp.quota:
                mycps.add(cp)
                cluster = cp.cluster

        try:
            test = cluster.name
        except:
            # this quota is not associated with a clusterpath -- so there is nothing to do here
            now = datetime.datetime.utcnow()
            msg = str(now) + ":noClusterName_for_quota:" + str(self) + ":" + self.get_updater()
            logger.info(msg)
            return

        subject = cluster.name + " QUMULO quota " + str(self.name)
        body = "Quota " + str(self.name)
        if pctusage > float(float(self.get_warnpct()) / float(100)):
            color = "magenta"
            eventtype = int(1)
            if nowutc > self.get_lastwarn():
                next_email = nowutc + self.get_warn_delay()
                self.set_lastwarn(next_email)
                subject = subject + " WARNING"
                body = body + " WARNING"
                sendmsg = True
                #logger.debug(body)
                logger.info(body)

        # check critical limit  (frequency in hours)
        if pctusage > float(float(self.get_criticalpct()) / float(100)):
            color = "orange"
            eventtype = int(2)
            if nowutc > self.get_lastcritical():
                next_email = nowutc + self.get_critical_delay()
                self.set_lastcritical(next_email)
                subject = subject + " CRITICAL "
                body = body + " CRITICAL"
                sendmsg = True
                #logger.debug(body)
                logger.info(body)

        # check full limit  (frequency in minutes)
        if pctusage > float(float(self.get_fullpct()) / float(100)):
            color = "red"
            eventtype = int(3)
            if nowutc > self.get_lastfull():
                next_email = nowutc + self.get_full_delay()
                self.set_lastfull(next_email)
                subject = subject + " FULL "
                body = body + " FULL"
                sendmsg = True
                #logger.debug(body)
                logger.info(body)

        # check for truly full
        if pctusage > float(float(100) / float(100)):
            color = "red"
            eventtype = int(4)
            # overide the FULL Frequency message trottle -- reduce it by a factor of 10 so that hourly messages become 6 minute messages
            # if self.get_fullpct() < 100:
            #    next_email = nowutc + (self.get_full_delay() / 10)
            subject = subject + " -- TRULY FULL -- WRITES HAVE STOPPED!"
            body = body + " -- TRULY FULL -- WRITES HAVE STOPPED!"
            sendmsg = True
            self.set_lastfull(next_email)

        self.set_colorname(color)

        mail_sent = 0
        next_email = next_email - nowutc
        if sendmsg is True:
            # during any development work we want to override sending emails to other sys admins
            # prevents hassling them (with bogus emails) when syncing from production back to development or integration
            deploy_env = "Unknown deploy environment"
            if hasattr(settings, 'DEPLOY_ENV'):
                deploy_env = settings.DEPLOY_ENV
            else:
                local_settings_file = os.path.join(os.path.dirname(__file__), os.pardir, 'settings.py')
                if os.path.exists(local_settings_file):
                    deploy_env = os.readlink(local_settings_file).split('.')[-1]

            contacts = []
            if str(deploy_env) is 'Production':
                contacts.append(str(self.primary))
                if self.secondary is not settings.EMAIL_HOST_USER:
                    contacts.append(str(self.secondary))
            else:
                contacts.append(str(settings.QRBA_ADMIN_EMAIL))

            subject = subject + " -- " + str(pctu) + " % used"
            nem = int(next_email)
            units = " seconds"
            if nem > 86400:
                nem = int(nem / 86400)
                units = " days"
            else:
                if nem > 3600:
                    nem = int(nem / 3600)
                    units = " hours"

            body = body + " usage -- percentage used = " + str(pctu) + "%\nNext email will be sent in " + str(
                nem) + units

            body = "Qumulo Cluster is: " + cluster.name + " ( " + str(cluster.ipaddr) + " )\n\n" + body

            if len(mycps) > 0:
                body = body + "\nClusterpath"
                if len(mycps) > 1:
                    body = body + "s"
                body = body + " impacted:\n"
                for cp in mycps:
                    body = body + "    " + str(cp) + "\n"

            myxports = set()
            for x in NfsExport.objects.all():
                if self == x.clusterpath.quota:
                    myxports.add(x)
            if len(myxports) > 0:
                body = body + "\nNFS Export"
                if len(myxports) > 1:
                    body = body + "s"
                body = body + " impacted:\n"
                for x in myxports:
                    body = body + "    " + str(x) + "\n"

            send_mail(subject, body, settings.EMAIL_HOST_USER, contacts)
            mail_sent = nowutc

        if eventtype > 0:
            # seconds until next message
            # msg = "    creating QuotaEvent  for " + str(self.name) + ", id = " + str(self.id) + ", qid = " + str(self.qid) + " and eventtype " + str(eventtype)
            # logger.info(msg)
            qe = QuotaEvent(quotaname=self.name, quotaid=self.qid, eventtype=eventtype, pctusage=pctusage, mailsent_utc=mail_sent,
                            seconds_to_next_email=next_email, colorname=color)
            qe.save()

    def percentage_used(self):
        color = self.get_colorname()
        pctu = 100.0 * float(self.get_pctusage())
        pctu = "{0:.1f}".format(pctu)
        return format_html('<span style="color: {};">{} %</span>',
                           color, pctu)

    percentage_used.admin_order_field = 'pctusage'

    def current_size(self):
        size = self.get_size()
        size = "{0:.2f}".format(size)
        # return format_html('<span>{}</span>', size )
        units = self.get_units()
        return format_html('<span>{}</span> {}', size, units.upper())

    current_size.admin_order_field = "size"

    def nextwarn(self):
        when = float(self.get_lastwarn())
        dt = datetime.datetime.fromtimestamp(when)
        if when != 0.0:
            color = self.get_colorname()
            return format_html('<span style="color: {};">{}</span>', color, str(dt))
        else:
            return format_html('<span>{}</span>', "Immediately")

    nextwarn.admin_order_field = "lastwarn"

    def nextcritical(self):
        when = float(self.get_lastcritical())
        dt = datetime.datetime.fromtimestamp(when)
        if when != 0.0:
            color = self.get_colorname()
            return format_html('<span style="color: {};">{}</span>', color, str(dt))
        else:
            return format_html('<span>{}</span>', "Immediately")

    nextcritical.admin_order_field = "lastcritical"

    def current_usage(self):
        # size = "{0:.2f}".format(self.usage) + " " + self.units.upper()
        usage = float(self.get_usage())
        if str(self.units) == "mb":
            usage = usage / settings.QUOTA_1MB
        if str(self.units) == "gb":
            usage = usage / settings.QUOTA_1GB
        if str(self.units) == "tb":
            usage = usage / settings.QUOTA_1TB
        if str(self.units) == 'pb':
            usage = usage / settings.QUOTA_1PB
        usage = "{0:.3f}".format(usage)
        units = self.get_units()
        # return format_html('<span>{}</span>', usage )
        return format_html('<span>{}</span> {}', usage, units.upper())

    current_usage.admin_order_field = "usage"

    def test_email(self):
        subject = "test from qrba"
        body = "body in test from qrba".strip().encode('ascii', 'ignore')
        fromaddr = settings.EMAIL_HOST_USER
        toaddr = ['some_developer@org.tld'.strip().encode('ascii', 'ignore')]
        e = "OK"
        try:
            send_mail(subject, body, fromaddr, toaddr, fail_silently=False)
        except SMTPException as e:
            pass
        return e

    def set_organization(self, org):
        # msg = "    setting quota organization for " + str(self.name) + ", id " + str(self.id) + " and organization " + str(self.organization) + " -- org is " + str(org)
        # logger.debug(msg)
        self.organization = org
        self.save()


##############################################################
#     ___              _        _   _                        #
#    / _ \ _   _  ___ | |_ __ _| | | |___  __ _  __ _  ___   #
#   | | | | | | |/ _ \| __/ _` | | | / __|/ _` |/ _` |/ _ \  #
#   | |_| | |_| | (_) | || (_| | |_| \__ \ (_| | (_| |  __/  #
#    \__\_\\__,_|\___/ \__\__,_|\___/|___/\__,_|\__, |\___|  #
#                                               |___/        #
##############################################################

class QuotaUsage(models.Model):
    size = models.BigIntegerField("Size in bytes", default=0)
    usage = models.BigIntegerField("Usage in bytes", default=0)
    quota = models.ForeignKey('provision.Quota', null=True)
    organization = models.ForeignKey('provision.Organization', null=True, related_name='org_by_quotausage')
    updated = models.DateTimeField("Updated:", auto_now_add=True)

    def __str__(self):
        name = str(self.quota) + "_usage"
        return str(name)

    def set_organization(self, org):
        self.organization = org
        self.save()

    def get_organization(self):
        return str(self.quota)


#############################################################
#     ___              _        _____                 _     #
#    / _ \ _   _  ___ | |_ __ _| ____|_   _____ _ __ | |_   #
#   | | | | | | |/ _ \| __/ _` |  _| \ \ / / _ \ '_ \| __|  #
#   | |_| | |_| | (_) | || (_| | |___ \ V /  __/ | | | |_   #
#    \__\_\\__,_|\___/ \__\__,_|_____| \_/ \___|_| |_|\__|  #
#                                                           #
#############################################################


class QuotaEvent(models.Model):
    quotaid = models.IntegerField(default=0)
    quotaname = models.CharField(max_length=200, default='unknown')
    eventtype = models.CharField('Event Type:', max_length=150, choices=EVENT_CHOICES, default='None')
    pctusage = models.FloatField(default=0.0)
    mailsent_utc = models.IntegerField(default=0)
    seconds_to_next_email = models.IntegerField(default=0)
    colorname = models.CharField(max_length=7, default='black')
    updated = models.DateTimeField("Updated:", auto_now_add=True)

    def __str__(self):
        name = str(self.quotaid)
        return str(name)

    def percentage_used(self):
        color = self.get_colorname()
        pctu = 100.0 * float(self.get_pctusage())
        pctu = "{0:.1f}".format(pctu)
        return format_html('<span style="color: {};">{} %</span>',
                           color, pctu)

    percentage_used.admin_order_field = 'pctusage'

    def get_pctusage(self):
        return self.pctusage

    def get_colorname(self):
        return self.colorname
#
#############################################################
#     ____ _           _                        _   _       #
#    / ___| |_   _ ___| |_ ___ _ __ _ __   __ _| |_| |__    #
#   | |   | | | | / __| __/ _ \ '__| '_ \ / _` | __| '_ \   #
#   | |___| | |_| \__ \ ||  __/ |  | |_) | (_| | |_| | | |  #
#    \____|_|\__,_|___/\__\___|_|  | .__/ \__,_|\__|_| |_|  #
#                                  |_|                      #
#############################################################

class Clusterpath(models.Model):
    dirid = models.BigIntegerField(default=-1)
    dirpath = models.CharField(verbose_name='Directory Path:', default=settings.DEFAULT_CLUSTERPATH, max_length=200,
                               help_text=settings.HELP_TEXT_CLUSTERPATH_DIRPATH)
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, help_text=settings.HELP_TEXT_CLUSTERPATH_NAMES)
    quota = models.ForeignKey(Quota, on_delete=models.CASCADE, help_text=settings.HELP_TEXT_CLUSTERPATH_QUOTA)
    organization = models.ForeignKey('provision.Organization', related_name='cp_org', null=True,
                                     help_text=settings.HELP_TEXT_ORGANIZATION)
    do_not_delete = models.BooleanField(default=False, help_text=settings.HELP_TEXT_DND)
    creator = models.CharField(default='unknown', max_length=200)
    updater = models.CharField(default='None', max_length=200)
    updated = models.DateTimeField(auto_now_add=True)

    def directory_path(self):
        return str(self.dirpath)

    directory_path.admin_order_field = 'dirpath'

    def __str__(self):
        return str(self.dirpath)

    def get_do_not_delete(self):
        return self.do_not_delete

    def get_id(self):
        return str(self.id)

    def get_dirid(self):
        return str(self.dirid)

    def get_dirpath(self):
        return str(self.dirpath)

    def get_creator(self):
        return str(self.creator)

    def get_updater(self):
        return str(self.updater)

    def set_updater(self, who):
        self.updater = who
        self.save()

    def get_cluster(self):
        return self.cluster

    def get_organization(self):
        return self.organization

    def set_dirid(self, did):
        self.dirid = did
        self.save()

    def set_do_not_delete(self, state):
        self.do_not_delete = state
        self.save()

    def set_dirpath(self, dp):
        self.dirpath = dp
        self.save()

    def set_organization(self, org):
        self.organization = org
        self.save()

    def save(self, create_on_cluster=False, *args, **kwargs):
        msg = "     in clusterpath.save -- dirpath = " + str(self.dirpath) + ", dirid = " + str(
            self.dirid) + ", id = " + str(self.id) + ", create_on_cluster is " + str(create_on_cluster)
        logger.debug(msg)

        (conninfo, creds) = qlogin(self.cluster.ipaddr, self.cluster.adminname, self.cluster.adminpassword,
                                   self.cluster.port)
        if not conninfo:
            msg = "could not connect to cluster " + str(self.cluster.name) + "  ... exiting"
            logger.critical(msg)
            sys.exit(-1)

        qid = 0
        if self.dirid < 0:
            create_on_cluster = True
            qid = -1

        dirpath = self.dirpath.encode('ascii', 'ignore')
        # Qumulo insists dirpaths must be absolute!
        if dirpath != '/':
            if settings.QUMULO_BASE_PATH not in dirpath:
                dirpath = settings.QUMULO_BASE_PATH + "/" + dirpath
                msg = "    added QUMULO_BASE_PATH to dirpath -- dirpath now " + str(dirpath)
                # logger.debug(msg)
            dirpath = re.sub("/$", "", dirpath)

        msg = "     dirpath is " + str(dirpath)
        # logger.debug(msg)
        dirpath = dirpath.replace("//", "/", 100)

        # enforce trailing '/' in dirpath
        if dirpath[len(dirpath) - 1:len(dirpath)] != '/':
            dirpath = dirpath + "/"
            msg = " dirpath updated to " + str(dirpath)
            logger.debug(msg)
        self.dirpath = dirpath

        if create_on_cluster is True:
            dirid = self.cluster.create_directory_on_cluster(conninfo, creds, dirpath)
            self.dirid = dirid
            need_to_create_quota = False
            try:
                qs = QRquota.get_quota_with_status(conninfo, creds, dirid)
                qid = int(qs.lookup('id'))
                msg = "      after get_quota_with_status for dirid qid = " + str(qid)
                #logger.debug(msg)
            except qumulo.lib.request.RequestError as err:
                need_to_create_quota = True
                qid = -1
                msg = "      error in get_quota_with_status for dirid " + str(dirid)
                #logger.debug(msg)

            msg = "     qid is " + str(qid) + " for dirpath " + str(dirpath) + " and dirid " + str(dirid)
            #logger.debug(msg)

            if need_to_create_quota is True:
                # all quota sizes are in the default units tb
                try:
                    quotasize = int(self.quota.get_size())
                    units = self.quota.get_units()
                except:
                    quotasize = int(settings.DEFAULT_CLUSTER_QUOTA_LIMIT)
                    units = 'tb'

                # msg = "   quotasize is " + str(quotasize) + " for " + str(self)
                # logger.debug(msg)

                if str(self.organization) != 'None':
                    try:
                        thisorg = Organization.objects.filter(id=self.organization)
                        if thisorg.count() == 1:
                            quotasize = int(settings.ORGANIZATION_QUOTA_LIMITS[thisorg[0].name])
                            units = 'tb'
                    except:
                        pass
                try:
                    quotasize = self.quota.get_size_times_units(quotasize, units)
                    msg = self.cluster.create_quota_on_cluster(conninfo, creds, dirid, dirpath, quotasize)
                    #logger.debug(msg)
                    if 'RequestError' not in msg:
                        qid = msg.split('qid:')
                        qid = int(qid[1])
                        msg = "           OK after create quota qid = " + str(qid) + " -- msg = " + str(msg)
                        #logger.debug(msg)
                        msg = "           self.dirid is " + str(self.dirid) + "  -- setting to qid = " + str(qid)
                        #logger.debug(msg)
                        self.dirid = qid
                    else:
                        msg = "   found RequestError in msg: " + str(msg)
                        #logger.debug(msg)

                except qumulo.lib.request.RequestError as err:
                    msg = "         RequestError: " + str(err) + " at create_quota_on_cluster for dirpath >" + str(
                        dirpath) + "<"
                    #logger.debug(msg)
            else:
                msg = "      need_to_create_quota is " + str(need_to_create_quota)
                #logger.debug(msg)
        else:
            msg = "        create_on_cluster is " + str(create_on_cluster)
            #logger.debug(msg)

        msg = "\n   before super self.dirid = " + str(self.dirid) + ", self.dirpath = " + str(
            self.dirpath) + ", self.id = " + str(self.id)
        #logger.debug(msg)
        self.showclusterpaths()

        super(Clusterpath, self).save(*args, **kwargs)
        # now = datetime.datetime.utcnow()
        # msg = str(now) + ":superClusterpath:" + str(self.dirid) + ":" + self.get_updater()
        # logger.info(msg)

        # msg = "   after super self.dirid = " + str(self.dirid) + ", self.dirpath = " + str(
        #    self.dirpath) + ", self.id = " + str(self.id) + "\n"
        #logger.debug(msg)
        #self.showclusterpaths()

        # Insure my quota's organization and qid are correct
        # msg = "    set_organization to " + str(self.organization) + " for cp " + str(self.id)
        # logger.debug(msg)
        self.quota.set_organization(self.get_organization())
        self.quota.set_qid(qid)

    def showclusterpaths(self):
        allclusterpaths = Clusterpath.objects.all()
        lcp = len(allclusterpaths)
        msg = "      found " + str(lcp) + " clusterpaths"
        #logger.debug(msg)
        msg = "      allclusterpaths:"
        #logger.debug(msg)
        for i in range(0, len(allclusterpaths)):
            msg = "        " + str(i) + ": " + str(allclusterpaths[i])
            # logger.debug(msg)
        #logger.debug("\n")

    def delete(self, using=None, keep_parents=False):
        msg = "    in delete clusterpath self = " + str(self)
        # logger.debug(msg)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if self.get_do_not_delete() is False:
            self.delete_from_cluster()
            super(Clusterpath, self).delete(using=using, keep_parents=keep_parents)
            msg = msg + ":deletedClusterpath:"
        else:
            msg = msg + ":attempted_deletedClusterpath:"
        msg = msg + str(self.dirpath) + ":" + self.get_updater()
        logger.info(msg)

    def delete_from_cluster(self):
        msg = "    in delete_from_cluster clusterpath self = " + str(self)
        #logger.debug(msg)
        if self.get_do_not_delete() is False:
            (conninfo, creds) = qlogin(self.cluster.ipaddr, self.cluster.adminname, self.cluster.adminpassword,
                                       self.cluster.port)
            if not conninfo:
                    msg = "could not connect to cluster " + str(self.cluster.name) + "  ... exiting"
                    logger.critical(msg)
                    sys.exit(-1)

            msg = self.cluster.delete_quota_on_cluster(conninfo, creds, id=self.dirid, path=self.dirpath)
            msg = "   deleted " + str(self.dirpath) + " on " + str(self.cluster.name) + " --  msg = " + msg
            # logger.debug(msg)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletedFromCluster_delete_quota_on_cluster:" + str(
                self.dirpath) + ":" + self.get_updater()
            logger.info(msg)

            nsfxparents = set()
            for x in NfsExport.objects.all():
                xrqs = x.restrictions.get_queryset()
                for xr in xrqs:
                    if xr == self:
                        nsfxparents.add(x)
            for x in nsfxparents:
                x.delete()

            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletedFromCluster_delete_nsfxparents:" + str(nsfxparents) + ":" + self.get_updater()
            logger.info(msg)
        else:
            msg = "   do_not_delete is True for cp " + str(self)
            #logger.debug(msg)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":attempted_deleteFromClusterClusterpath:" + str(self.dirpath) + ":" + self.get_updater()
            logger.info(msg)

        ### need to deal with a quota deletes here --- will have to check for quota use on all clusters/clusterpaths

#######################################
#    ____                       _     #
#   |  _ \ ___ _ __   ___  _ __| |_   #
#   | |_) / _ \ '_ \ / _ \| '__| __|  #
#   |  _ <  __/ |_) | (_) | |  | |_   #
#   |_| \_\___| .__/ \___/|_|   \__|  #
#             |_|                     #
#######################################

class Report(models.Model):
    name = models.CharField(max_length=100, null=True, default='unknownReportname')
    type = models.CharField("Report Type:", max_length=100)
    cadence = models.IntegerField(default=-1)
    units = models.CharField('Cadence units:', max_length=20, choices=CADENCE_CHOICES, default='h')
    organization = models.ForeignKey('provision.Organization', null=True, related_name='report_list_of_orgs')
    creator = models.CharField(default='unknown', max_length=200)
    updater = models.CharField(default='None', max_length=200)
    updated = models.TimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_type(self):
        return self.type

    def get_cadence(self):
        return self.cadence

    def get_creator(self):
        return str(self.creator)

    def get_updater(self):
        return str(self.updater)

    def set_updater(self, who):
        self.updater = who
        self.save()

    def set_organization(self, org):
        # msg = "    setting quota organization for " + str(self.name) + ", id " + str(self.id) + " and organization " + str(self.organization) + " -- org is " + str(org)
        # logger.debug(msg)
        self.organization = org
        self.save()

    def delete(self, using=None, keep_parents=False):
        super(Report, self).delete()
        now = datetime.datetime.utcnow()
        msg = str(now) + ":deleteReport:" + str(self.name) + ":" + self.get_updater()
        logger.info(msg)

#################################################################
#     ___                        _          _   _               #
#    / _ \ _ __ __ _  __ _ _ __ (_)______ _| |_(_) ___  _ __    #
#   | | | | '__/ _` |/ _` | '_ \| |_  / _` | __| |/ _ \| '_ \   #
#   | |_| | | | (_| | (_| | | | | |/ / (_| | |_| | (_) | | | |  #
#    \___/|_|  \__, |\__,_|_| |_|_/___\__,_|\__|_|\___/|_| |_|  #
#              |___/                                            #
#################################################################

class Organization(models.Model):
    name = models.CharField(max_length=50, null=True, default='unknownOrganization')
    ipzones = models.TextField(default='')
    adminhosts = models.TextField(default='')
    hosts = models.TextField(default='')
    clusterpaths = models.ManyToManyField(Clusterpath, related_name='orgs_list_of_cps')
    reports = models.ManyToManyField(Report, related_name='reports_by_rog')
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # logger.debug("saving org: " + str(self.name))
        super(Organization, self).save(*args, **kwargs)
        # now = datetime.datetime.utcnow()
        # msg = str(now) + ":superOrganization:" + str(self.name) + ":no_updater"
        #logger.info(msg)

        # Insure superusers have access to all organizations
        sysads = Sysadmin.objects.all()
        for sa in sysads:
            if sa.is_a_superuser:
                sa.organizations.add(self)

        # myzones = self.get_ipzones()
        # msg = "  org " + str(self.name) + ":"
        # for z in myzones:
        #    ipz = IPzone.objects.filter(name=z)
        #   if ipz.count() > 0:
        #        msg = str(ipz[0]) + ", " + msg
        #msg = re.sub(",$", "", msg)
        #logger.debug(msg)

    def get_ipzones(self):
        zlist = []
        ipzones = str(self.ipzones)
        for z in ipzones.split(", "):
            z = z.replace("u'", "'", 1000)
            z = re.sub("^\[", "", z)
            z = re.sub("\]$", "", z)
            if z != '':
                zlist.append(z)
        return zlist

    def set_ipzones(self, zlist):
        ipzones = ''
        zlist.sort(reverse=True)
        # print( " zlist is " + str(zlist))
        for z in zlist:
            ipzones = str(z) + ", " + ipzones
        self.ipzones = re.sub(", $", "", ipzones)
        #msg = "  ipzone for " + str(self.name) + " updated to " + str(self.ipzone)
        #logger.debug(msg)
        # print( msg )
        self.save()

    def append_ipzone(self, zone):
        ipzlist = self.get_ipzones()
        ipzlist.append(zone)
        zones = ''
        ipzlist.sort()
        for z in ipzlist:
            zones = str(z) + "," + zones
        self.ipzones = re.sub(",$", "", zones)
        self.save()

    def get_hosts(self):
        hlist = []
        hosts = str(self.hosts)
        for h in hosts.split(","):
            h = h.replace("u'", "'", 1000)
            h = re.sub("^\[", "", h)
            h = re.sub("\]$", "", h)
            h = h.strip().encode('ascii', 'ignore')
            if h != '' and h != '0.0.0.0':
                hlist.append(h)
        return hlist

    def set_hosts(self, hlist):
        hosts = ''
        hlist.sort()
        for h in hlist:
            if '0.0.0.0' not in str(h):
                hosts = str(h) + "," + hosts
        self.hosts = re.sub(",$", "", hosts)
        self.save()

    def append_host(self, host):
        hostlist = self.get_hosts()
        hostlist.append(host)
        hosts = ''
        hostlist.sort()
        for h in hostlist:
            if '0.0.0.0' not in str(h):
                hosts = str(h) + "," + hosts
        self.hosts = re.sub(",$", "", hosts)
        self.save()

    def check_ipzones(self):
        dcipzones = self.get_ipzones_from_windc()
        ipzones = self.get_ipzones()
        newzonesset = set(dcipzones).difference(ipzones)
        newzones = []
        activity = {}
        activity['newzones'] = ''
        activity['dcipzones'] = ''
        activity['ipzone'] = ''
        for z in newzonesset:
            newzones.append(z)
        if len(newzones) > 0:
            self.set_ipzones(newzones)
            activity['newzones'] = str(newzones)
        else:
            activity['dcipzones'] = str(dcipzones)
            activity['ipzone'] = str(ipzones)
        return activity

    def check_hosts(self):
        currenthosts = self.get_hosts()
        dchosts = self.get_hosts_from_windc()
        newhostsset = set(dchosts).difference(currenthosts)
        removedhostsset = set(currenthosts).difference(dchosts)
        removedhosts = []
        for h in removedhostsset:
            removedhosts.append(h)

        newhosts = []
        activity = {}
        for h in newhostsset:
            newhosts.append(h)

        if len(currenthosts) == int(0) and len(newhosts) > int(0):
            self.set_hosts(newhosts)

        activity['organization'] = str(self.name)
        activity['lendchosts'] = str(len(dchosts))
        activity['lencurrenthosts'] = str(len(currenthosts))
        activity['newhosts'] = str(newhosts)
        activity['removedhosts'] = str(removedhosts)
        return activity

    def get_ipzones_from_windc(self):
        zonesset = set()
        for wdc in WinDC.objects.all():
            wdczones = wdc.get_ipzones()
            for z in wdczones:
                zonesset.add(z)
        zones = []
        for z in zonesset:
            zones.append(z)
        if len(zones) > 1:
            zones.sort()
        return zones

    def get_hosts_from_windc(self):
        hostsset = set()
        for wdc in WinDC.objects.all():
            wdchostsbyzone = wdc.get_hosts_by_ipzone()
            for z in wdchostsbyzone.iterkeys():
                for h in wdchostsbyzone[z]:
                        hostsset.add(h)
        hosts = []
        for h in hostsset:
            hosts.append(h)
        if len(hosts) > 1:
            hosts.sort()
        return hosts

    def set_clusterpaths(self, cplist):
        ''' Replaces the existing list of clusterpaths with the given list '''
        # msg = "   clusterpaths: " + str(clusterpaths)
        # logger.debug(msg)
        if self.clusterpaths.all().count() > 0:
            self.clusterpaths.all().delete()
        for cp in cplist:
            # msg = "    cp is " + str(cp)
            # logger.debug(msg)
            self.clusterpaths.add(cp)
        self.save()

    def get_adminhosts(self):
        hlist = []
        hosts = str(self.adminhosts)
        for h in hosts.split(","):
            h = h.replace("u'", "'", 1000)
            h = re.sub("^\[", "", h)
            h = re.sub("\]$", "", h)
            if h != '':
                hlist.append(h)
        return hlist

    def set_adminhosts(self, hlist):
        hosts = ''
        hlist.sort()
        for h in hlist:
            hosts = str(h) + "," + hosts
        self.adminhosts = re.sub(",$", "", hosts)
        self.save()

    def append_adminhost(self, host):
        hostlist = self.get_adminhosts()
        hostlist.append(host)
        hosts = ''
        hostlist.sort()
        for h in hostlist:
            hosts = str(h) + "," + hosts
        self.adminhosts = re.sub(",$", "", hosts)
        self.save()

    def get_ipmarker(self):
        marker = settings.HOST_STATISTICS_PREFIX + str(self.id)
        return marker


######################################
#    ___ ____                        #
#   |_ _|  _ \ _______  _ __   ___   #
#    | || |_) |_  / _ \| '_ \ / _ \  #
#    | ||  __/ / / (_) | | | |  __/  #
#   |___|_|   /___\___/|_| |_|\___|  #
#                                    #
######################################


class IPzone(models.Model):
    name = models.CharField('Name:', max_length=250, help_text=settings.HELP_TEXT_IPZONE)
    hostnames = models.TextField(default='', help_text=settings.HELP_TEXT_IPZONE_HOSTNAMES)
    ipaddrs = models.TextField(default='', blank=True)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, null=True, related_name='ad_zone_org',
                                     help_text=settings.HELP_TEXT_ORGANIZATION)
    immutable = models.BooleanField(default=False, help_text=settings.HELP_TEXT_IMMUTABLE)
    initialized = models.BooleanField(default=False)
    creator = models.CharField(default='unknown', max_length=200)
    updater = models.CharField(default='None', max_length=200)
    ipzmarker = models.TextField(default='unset')
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('id',)
        verbose_name = "IP Zone"
        verbose_name_plural = "IP Zones"

    def __str__(self):
        return self.name

    def set_immutable(self, state):
        self.immutable = state
        self.save()

    def is_immutable(self):
        return self.immutable

    def get_creator(self):
        return str(self.creator)

    def get_updater(self):
        return str(self.updater)

    def set_updater(self, who):
        self.updater = who
        self.save()

    def zonename_in_single_element_list(self, iplist):
        ips = []
        if len(iplist) > 0:
            ips = str(iplist[0]).split(',')

        for z in IPzone.objects.all():
            for ip in ips:
                ip = ip.strip().encode('ascii', 'ignore')
                if ip != '' and ip in str(z.name):
                    return True
        return False

    def get_ipzone_marker(self):
        return self.ipzmarker

    def set_ipzone_marker(self):
        if self.ipzmarker == 'unset':
            zones = IPzone.objects.all()
            zones = zones.count()
            third = int(zones / 254) + 1
            fourth = zones % 254
            self.ipzmarker = settings.IPZONE_MARKER_BASE + str(third) + "." + str(fourth)
            self.save()

    def save(self, new_host=False, *args, **kwargs):
        msg = "saving ipzone: " + str(self.name) + "\n    new_host: " + str(new_host)
        # logger.info(msg)
        if len(self.ipaddrs) > 0 or len(self.hostnames) > 0:
            msg = "    ipaddrs: " + str(self.ipaddrs) + "\n    hostnames: " + str(self.hostnames)
            #logger.info(msg)

        # Save initial objects
        init_hostnames = self.get_hostnames()
        ihs = str(init_hostnames)
        msg = "   ihs: " + str(ihs)
        #logger.debug(msg)
        has_parens = False
        for c in ihs.split():
            if '(' in c:
                has_parens = True
                break

        if self.initialized is False:
            self.initialized = True
            super(IPzone, self).save(*args, **kwargs)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":initializedIpzone:" + str(self.name) + ":" + self.get_updater()
            logger.info(msg)

        # but... do not allow editing of AD zones
        if self.is_immutable() is True:
            msg = "   immutable: " + str(self) + " " + str(self.is_immutable())
            #logger.debug(msg)
            msg = "   hasparens: " + str(self) + " " + str(has_parens)
            #logger.debug(msg)
            if 'immutable' in self.name:
                msg = "   found immutable in " + str(self.name)
                #logger.debug(msg)
                # lock the door
                self.name = re.sub("immutable", "", self.name)
                super(IPzone, self).save(*args, **kwargs)
                now = datetime.datetime.utcnow()
                msg = str(now) + ":super2IPzone:" + str(self.name) + ":" + self.get_updater()
                #logger.info(msg)
            else:
                msg = "   immutable not in self.name for " + str(self.name)
                #logger.debug(msg)
            return
        else:
            msg = "    IPzone " + str(self) + " is not immutable"
            #logger.debug(msg)

        ipzmarker = self.get_ipzone_marker()

        hnips = set()
        hnipstr = self.hostnames
        hnipstr = hnipstr.replace("\r", "", 10000).encode('ascii', 'ignore')
        hniplist = []
        if len(hnipstr) > 0:
            hniplist = hnipstr.split("\n")

        # deal with input from a 'showmount -e' such as:
        # ISB-MADIS-PROD
        # ISB-ROOT,ISB,ISB-AWIPS-ALPS,ISB-MADIS,ISB-MADIS-PROD,host.domain.org.tld,host2.domain.org.tld
        # These enties must contain at least on IPzone name
        if self.zonename_in_single_element_list(hniplist) is True:
            # line = hniplist[0].split(",")
            allipzones = IPzone.objects.all()
            hniplist = []
            if len(hniplist) > 1:
                hniplist = hniplist[0].split(',').encode('ascii', 'ignore')
            for horz in hniplist:
                horz = str(horz)
                horz = re.sub("\'", "", horz)
                horz = horz.strip().encode('ascii', 'ignore')
                if "." in horz:
                    # is an IP address
                    msg = "   addding ip " + str(horz)
                    #logger.debug(msg)
                    hnips.add(horz)
                else:
                    # is an IPzone name
                    for z in allipzones:
                        if z == self:
                            continue
                        zonename = z.name
                        if "/" in zonename:
                            zonename = zonename.split("/")
                            zonename = zonename[len(zonename) - 1]
                            if zonename == horz:
                                msg = "  adding ipzone " + str(z.name)
                                #logger.debug(msg)
                                zips = z.get_ipaddrs()
                                for zip in zips:
                                    hnips.add(zip)
            hniplist = []
            for ip in hnips:
                ip = str(ip)
                hniplist.append(ip.strip().encode('ascii', 'ignore'))
            hnips = set()

        if len(hniplist) > 0:
            msg = "       hniplist: " + str(hniplist)
            #logger.debug(msg)

        for hnip in hniplist:
            if " (" in str(hnip):
                hnip = str(hnip).split("(")
                ip = str(hnip[1].replace(")", ""))
                ip = ip.strip().encode('ascii', 'ignore')
            else:
                # accept ip ranges
                ip = hnip
                if not "/" in hnip:
                    try:
                        ip = socket.gethostbyname(hnip)
                    except BaseException as msg:
                        ip = '0.0.0.0'
                        #msg = "BaseException 1 getting hostname for " + str(hnip) + " -- msg = " + str(msg)
                        #logger.info(msg)
            if ip != '0.0.0.0':
                hnips.add(ip)

        if len(hnips) > 0:
            msg = "       hnips: " + str(hnips)
            #logger.debug(msg)

        ips = set()
        ipslist = str(self.ipaddrs).split(",")
        for ip in ipslist:
            ip = str(ip).strip().encode('ascii', 'ignore')
            if ip != "" and ip != "''":
                ips.add(ip)
        msg = "   ips are " + str(ips)
        #logger.debug(msg)

        # If a host appears in hostnames and it is not in the ip address list, then it (they) were added in the GUI
        newhosts = hnips.difference(ips)
        hnipslist = []
        for h in hnips:
            hnipslist.append(h)
        hnipslist.sort(reverse=True)

        msg = "   hnipslist are " + str(hnipslist)
        #logger.debug(msg)

        msg = "len(newhosts) <= 0 == " + str(len(newhosts))
        #logger.debug(msg)


        if len(newhosts) > 0:
            msg = "    newhosts are: " + str(newhosts)
            #logger.debug(msg)
            self.ipaddrs = ''
            self.hostnames = ''
            for ip in hnipslist:
                ip = str(ip).strip().encode('ascii', 'ignore')
                if ip != ipzmarker and ip != 'unset':
                    self.ipaddrs = ip + "," + self.ipaddrs
                hn = str(ip)
                if not "/" in ip and ip != ipzmarker:
                    # accept ip ranges
                    try:
                        hn = socket.gethostbyaddr(ip)
                        hn = str(hn[0]).encode('ascii', 'ignore')
                    except BaseException as msg:
                        # pass
                        #hn = str(ip)
                        msg = "BaseException 2 getting hostname for " + str(ip) + " -- msg = " + str(msg)
                        logger.debug(ip)
                else:
                    hn = "IPrange"

                if settings.IPZONE_MARKER_BASE not in ip:
                    self.hostnames = hn + " (" + str(ip) + ")\n" + self.hostnames
                else:
                    msg = "   skipping ip " + str(ip)
                    #logger.info(msg)
            self.ipaddrs = re.sub(",$", "", self.ipaddrs)
            if ipzmarker not in self.ipaddrs and ipzmarker != 'unset':
                if self.ipaddrs != '':
                    self.ipaddrs = self.ipaddrs + "," + ipzmarker
                else:
                    self.ipaddrs = ipzmarker
            self.hostnames = re.sub("\n$", "", self.hostnames)
            if len(self.ipaddrs) > 0:
                msg = "   ipaddrs are now: " + str(self.ipaddrs)
                # logger.debug(msg)
            if len(self.hostnames) > 0:
                msg = "   hostnames are now: " + str(self.hostnames)
                #logger.debug(msg)

        # If a host appears in the ip address list but not in hostnames, then it (they) were removed in the GUI
        if len(hnips) > 0:
            msg = "len(hnips) = " + str(len(hnips))
            # logger.debug(msg)
        if len(hnipslist) > 0:
            msg = "len(hnipslist) = " + str(len(hnipslist))
            # logger.debug(msg)

        if hnipslist != ipslist and len(hnipslist) != 0:
            removedhosts = ips.difference(hnips)
            if len(removedhosts) > 0:
                msg = "    removedhosts are: " + str(removedhosts)
                #logger.info(msg)

                # tricky ... on initialization len(hnip) is 0 but removed hosts maybe non-zero.
                # So do a swap and let code below handle this case.
                if len(hnips) == 0 or new_host is True:
                    for rn in removedhosts:
                        hnips.add(rn)
                    removedhosts = []

                msg = "    removedhosts are now: " + str(removedhosts)
                #logger.info(msg)
                msg = "    hnips are now: " + str(hnips)
                # logger.info(msg)

            if new_host is True:
                for rn in removedhosts:
                    hnips.add(rn)
                    msg = "    hnips (2) are now: " + str(hnips)
                    #logger.info(msg)

            self.ipaddrs = ''
            ipsset = set()
            if ipzmarker != 'unset':
                ipsset.add(ipzmarker)
            # hostname ips
            for h in hnips:
                if h not in str(removedhosts):
                    ipsset.add(h)
                # ips from ipaddrs
                for i in ips:
                    if len(removedhosts) > 0:
                        if i not in str(removedhosts):
                            ipsset.add(i)

                # new host added via the gui
                if (len(removedhosts) == 0 and (ipslist != hniplist)) or not has_parens:
                    if h not in str(removedhosts):
                        ipsset.add(h)

            ipslist = []
            for h in ipsset:
                ipslist.append(h)
            ipslist.sort()
            msg = "ipslist = " + str(ipslist)
            #logger.debug(msg)

            hostnames_by_ip = {}
            ips_by_hostname = {}
            for ip in ipslist:
                ip = str(ip).strip().encode('ascii', 'ignore')
                if ip != ipzmarker and ip != 'unset':
                    self.ipaddrs = ip + "," + self.ipaddrs
                hn = str(ip)
                if "/" not in ip and ip != ipzmarker:
                    try:
                        hn = socket.gethostbyaddr(str(ip).encode('ascii', 'ignore'))
                        hn = str(hn[0]).encode('ascii', 'ignore')
                    except BaseException as msg:
                        # pass
                        #hn = str(ip)
                        msg = "BaseException 3 getting hostname for " + str(ip) + " -- msg = " + str(msg)
                        logger.info(msg)
                else:
                    hn = "IP range"
                if settings.IPZONE_MARKER_BASE not in ip:
                    hostnames_by_ip[ip] = hn
                    ips_by_hostname[hn] = ip
                # else:
                #msg = "   skipping hn " + hn + " due to ip " + str(ip) + " in ip marker base " + settings.IPZONE_MARKER_BASE
                    #logger.info(msg)
            self.ipaddrs = re.sub(",$", "", self.ipaddrs)
            if ipzmarker not in self.ipaddrs and ipzmarker != 'unset':
                if self.ipaddrs != '':
                    self.ipaddrs = self.ipaddrs + "," + ipzmarker
                else:
                    self.ipaddrs = ipzmarker

            # self.hostnames = ''
            # for ip in hostnames_by_ip.keys():
            #    self.hostnames = hostnames_by_ip[ip] + " (" + str(ip) + ")\n" + self.hostnames
            self.hostnames = ""
            hostnames = ips_by_hostname.keys()
            hostnames.sort(reverse=True)
            for hn in hostnames:
                self.hostnames = str(hn) + " (" + str(ips_by_hostname[hn]) + ")\n" + self.hostnames

            self.hostnames = re.sub("\n$", "", self.hostnames)
            if len(self.ipaddrs) > 0:
                msg = "   2 -- ipaddrs are now: " + str(self.ipaddrs)
                # logger.info(msg)
            if len(self.hostnames) > 0:
                msg = "   2 -- hostnames are now:\m" + str(self.hostnames)
                #logger.info(msg)

        super(IPzone, self).save(*args, **kwargs)
        now = datetime.datetime.utcnow()
        msg = str(now) + ":super3IPzone:" + str(self.name) + ":" + self.get_updater()
        #logger.info(msg)

        ###
        #   Locate and save (update) associated NFS Restrictions and then NFS Exports, but only if immutable flag is False (the default -- so that GUI created objects are deleted)
        #   this code is necessarily repeated in post_save_ipzone()
        if self.is_immutable() is False:
            rpset = set()
            for r in Restriction.objects.all():
                ipzones = r.get_ipzones()
                for z in ipzones:
                    if self == z:
                        msg = "   saving restriction " + str(r)
                        #logger.debug(msg)
                        #r.save()
                        rpset.add(r)

            for r in rpset:
                msg = "   saving restriction " + str(r)
                #logger.debug(msg)
                r.save()

            nsfxparents = set()
            for x in NfsExport.objects.all():
                xrqs = x.restrictions.get_queryset()
                for xr in xrqs:
                    for r in rpset:
                        if r == xr:
                            nsfxparents.add(x)
            for x in nsfxparents:
                msg = "   saving export " + str(x)
                #logger.debug(msg)
                x.save(update_on_cluster=True)

        msg = "   leaving ipzone: " + str(self.name) + "\n    new_host: " + str(new_host)
        # logger.info(msg)
        if len(self.ipaddrs) > 0 or len(self.hostnames) > 0:
            msg = "\nipaddrs:\n" + str(self.ipaddrs) + "\nhostnames:\n" + str(self.hostnames) + "\n"
            #logger.info(msg)

    def get_ipaddrs(self):
        iplist = []
        for ip in self.ipaddrs.split(","):
            ip = str(ip).strip().encode('ascii', 'ignore')
            if ip != '' and ip != '0.0.0.0' and ip != 'unset':
                iplist.append(ip)
            else:
                msg = "   get_ipaddrs skipping ip " + str(ip)
                #logger.info(msg)
        if len(iplist) > 1:
            iplist.sort()
        return iplist

    def get_hostnames(self):
        hostnames = []
        for hn in self.hostnames.split("\n"):
            hn = str(hn).strip().encode('ascii', 'ignore')
            if 'unset' not in hn:
                hostnames.append(str(hn).strip().encode('ascii', 'ignore'))
            else:
                msg = "   get_hostnames skipping hn " + str(hn)
                #logger.info(msg)
        if len(hostnames) > 1:
            hostnames.sort()
        return hostnames

    def set_ipaddrs(self, iplist, new_host=False):
        self.ipaddrs = ''
        for ip in iplist:
            ip = str(ip).strip().encode('ascii', 'ignore')
            if ip != '0.0.0.0' and ip != '' and 'unset' not in ip:
                self.ipaddrs = ip + "," + self.ipaddrs
            else:
                msg = "   set_ipaddrs skipping ip " + str(ip)
                #logger.info(msg)
        self.ipaddrs = re.sub(",$", "", self.ipaddrs)
        self.save(new_host=new_host)
        self.set_hostnames()

    def set_hostnames(self, new_host=False):
        ips = str(self.ipaddrs)
        ips = ips.split(',')
        hostnames = []
        for ip in ips:
            ip = str(ip).strip().encode('ascii', 'ignore')
            if ip != '' and ip != '0.0.0.0' and settings.IPZONE_MARKER_BASE not in ip:
                qs = Host.objects.filter(ipaddr=ip)
                if qs.count() == 1:
                    name = qs[0].name + " (" + str(ip) + ")"
                else:
                    if "-" in str(ip) or "/" in str(ip):
                        name = "IP range (" + str(ip) + ")"
                    else:
                        name = str(ip) + " (" + str(ip) + ")"
                hostnames.append(name)
            else:
                msg = "   set_hostnames skipping ip " + str(ip)
                #logger.info(msg)
        names = ''
        hostnames.sort(reverse=True)
        for h in hostnames:
            names = h + "\n" + names
        self.hostnames = re.sub("\n$", "", names)
        msg = "    ipzone " + str(self.name) + " hostnames are " + str(self.hostnames)
        #logger.debug(msg)
        self.save(new_host=new_host)

    def delete(self, using=None, keep_parents=False):
        now = datetime.datetime.utcnow()
        msg = str(now)
        if self.is_immutable() is False:
            self.delete_from_cluster()
            super(IPzone, self).delete(using=using, keep_parents=keep_parents)
            msg = msg + ":deletedIPZone:"
        else:
            msg = msg + ":attempted_deleteIPZone:"
        msg = msg + str(self.name) + ":" + self.get_updater()
        logger.info(msg)

    def delete_from_cluster(self):
        if self.is_immutable() is False:
            rparents = set()
            for r in Restriction.objects.all():
                rzones = r.get_ipzones()
                for rz in rzones:
                    if rz == self:
                        rparents.add(r)
            nsfxparents = set()
            for x in NfsExport.objects.all():
                xrqs = x.get_restrictions()
                for xr in xrqs:
                    for r in rparents:
                        if r == xr:
                            nsfxparents.add(x)

            now = datetime.datetime.utcnow()
            msg = str(now)
            if len(nsfxparents) > 0:
                for x in nsfxparents:
                    x.delete()
                msg = msg + ":deletedIPZoneFromCluster_nsfxparents:" + str(nsfxparents)
            else:
                msg = msg + ":deleteIPZoneFromCluster_no_nfsparents:"
            msg = msg + ":" + self.get_updater()
            logger.info(msg)

            now = datetime.datetime.utcnow()
            msg = str(now)
            if len(rparents) > 0:
                for r in rparents:
                    r.delete()
                msg = msg + ":deletedIPZoneFromCluster_rparents:" + str(rparents)
            else:
                msg = msg + ":deleteIPZoneFromCluster_no_rparents:"
            msg = msg + ":" + self.get_updater()
            logger.info(msg)
        else:
            now = datetime.datetime.utcnow()
            msg = str(now) + ":attempted_deleteIPZoneFromCluster:" + str(self.name) + ":" + self.get_updater()
            logger.info(msg)

    def find_ipzone_from_iplist(self, thisorg, iplist):
        """
        returns the IPzone who's ipaddrs have the most matches to the given iplist or an empty IPZone query set
        """
        ipinfo_by_zone = {}
        ipset = set(iplist)
        ipzones = IPzone.objects.filter(organization=thisorg)
        for z in ipzones:
            ipinfo_by_zone[z.name] = {}
            zips = set(z.get_ipaddrs())
            # for ip in z.get_ipaddrs():
            #    zips.add(ip)

            if len(zips) > 0:
                ipinfo_by_zone[z.name]['nips'] = len(zips)
                ipinfo_by_zone[z.name]['ipcount'] = 0
                for ip in zips:
                    if ip in str(ipset):
                        msg = "      " + str(ip) + " in ipset"
                        ipinfo_by_zone[z.name]['ipcount'] = ipinfo_by_zone[z.name]['ipcount'] + 1
                        # else:
                        #    msg = "      " + str(ip) + " NOT in ipset"
                        #logger.debug(msg)

                msg = "    ipcount, nips = " + str(float(ipinfo_by_zone[z.name]['ipcount'])) + ", " + str(
                    float(ipinfo_by_zone[z.name]['nips']))
                #logger.debug(msg)

            try:
                ipinfo_by_zone[z.name]['pct'] = float(ipinfo_by_zone[z.name]['ipcount']) / float(
                    ipinfo_by_zone[z.name]['nips'])
            except:
                ipinfo_by_zone[z.name]['pct'] = 0.0

        bypct = {}
        print("bypct:")
        for z in ipinfo_by_zone.keys():
            bypct[ipinfo_by_zone[z]['pct']] = z
            msg = "     ipinfo_by_zone[" + str(z) + "]['pct'] = " + str(ipinfo_by_zone[z]['pct'])
            #logger.debug(msg)

        pcts = bypct.keys()
        z = ''
        if len(pcts) > 0:
            pcts.sort(reverse=True)
            msg = "   pcts[0] = " + str(pcts[0])
            #logger.debug(msg)
            if pcts[0] > 0.0:
                z = IPzone.objects.filter(name=bypct[pcts[0]])
                if z.count() > 0:
                    z = z[0]
            else:
                z = ''
        return z



############################
#    _   _           _     #
#   | | | | ___  ___| |_   #
#   | |_| |/ _ \/ __| __|  #
#   |  _  | (_) \__ \ |_   #
#   |_| |_|\___/|___/\__|  #
#                          #
############################

class Host(models.Model):
    name = models.CharField(max_length=100, null=True, default='unknownHostname')
    ipaddr = models.CharField(max_length=50, null=True, default='unknownHostipaddr')
    # organization = models.ForeignKey(Organization)
    organization = models.ForeignKey(Organization, null=True,
                                     related_name='host_org', help_text=settings.HELP_TEXT_ORGANIZATION)
    ipzone = models.ForeignKey(IPzone, default='', null=True)
    updated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if 'unknownHostname' in str(self.name):
            return str(self.ipaddr)
        else:
            return self.name.lower()

    # def save(self, *args, **kwargs):
    #    #logger.debug("  saving host: " + str(self.name))
    #    super(Host, self).save(*args, **kwargs)

    def getip(self):
        return self.ipaddr

    def get_organization(self):
        return self.organization

    def check_hostname(self):
        now = timezone.now()
        hostname = str(self.name)
        ipaddr = str(self.ipaddr)
        state = False

        if "/" not in ipaddr:
            try:
                dnshostname = socket.gethostbyaddr(ipaddr)
                dnshostname = str(dnshostname[0])
            except BaseException as msg:
                dnshostname = "unknown"
                msg = "BaseException 4 getting hostname for " + str(ipaddr) + " -- msg = " + str(msg)
                #logger.debug(msg)
        else:
            dnshostname = "IP range"

        if dnshostname not in hostname:
            self.name = dnshostname
            self.updated = now
            self.save()
            state = True
            # msg = "hostname for " + str(ipaddr) + " updated to " + str(dnshostname)
            # logger.debug(msg)
        return state

    def check_hostip(self):
        now = timezone.now()
        hostname = str(self.name)
        ipaddr = str(self.ipaddr)
        state = False

        msg = "check_hostip for " + str(hostname)
        #logger.debug(msg)
        try:
            dnsipaddress = socket.gethostbyname(hostname)
        except socket.error:
            dnsipaddress = "0.0.0.0"
        msg = "dnsipaddress = " + str(dnsipaddress)
        #logger.debug(msg)

        if dnsipaddress not in ipaddr:
            self.ipaddr = dnsipaddress
            self.updated = now
            msg = "ipaddress for " + str(hostname) + " updated to " + str(dnsipaddress)
            #logger.debug(msg)
            self.save()
            state = True
        return state

    def add_host_none(self):
        lh = Host.objects.filter(ipaddr=settings.LOCALHOST)
        if lh.count() < 1:
            lh = Host(name="None", ipaddr=settings.LOCALHOST)
            lh.save()

##############################################################
#    ____  _   _ ____      _                       _         #
#   |  _ \| \ | / ___|  __| | ___  _ __ ___   __ _(_)_ __    #
#   | | | |  \| \___ \ / _` |/ _ \| '_ ` _ \ / _` | | '_ \   #
#   | |_| | |\  |___) | (_| | (_) | | | | | | (_| | | | | |  #
#   |____/|_| \_|____/ \__,_|\___/|_| |_| |_|\__,_|_|_| |_|  #
#                                                            #
##############################################################

class DNSdomain(models.Model):
    name = models.CharField(max_length=256, null=True, default='unknownDNSdomain')
    windcs = models.TextField(default='')
    updated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Windows AD Domain"
        verbose_name_plural = "Windows AD Domains"

    def save(self, *args, **kwargs):
        # msg = "saving dnsdomain: " + str(self.name)
        # logger.debug(msg)
        super(DNSdomain, self).save(*args, **kwargs)

    def get_windcs(self):
        dclist = []
        windcs = str(self.windcs)
        windcs = windcs.split(',')
        for c in windcs:
            if c != '':
                dclist.append(c)
        return dclist

    def check_dcs(self):
        state = False
        msdcs = self.get_dcs_from_msdcs()
        windcs = self.get_windcs()
        newdcsset = set(msdcs).difference(windcs)
        newdcs = []
        for d in newdcsset:
            newdcs.append(d)
        dcstr = ''
        if len(newdcs) > 0:
            alldcs = WinDC.objects.all()
            dcnames = ""
            for x in alldcs:
                x = str(x)
                x = x.split(":")
                x[0] = x[0].encode('ascii', 'ignore')
                dcnames = dcnames + " " + x[0]

            for dc in newdcs:
                if WinDC.objects.filter(name=dc).count() == 0:
                    dcstr = dcstr + ","
                    thisdc = WinDC(name=dc, dnsdomain=self.name)
                    thisdc.save()
                    state = True
        if state is True:
            dcstr = re.sub(",$", "", dcstr)
            self.windcs = dcstr
            self.save()
        return state

    def get_dcs_from_msdcs(self):
        cmd = "/usr/bin/host -t srv _ldap._tcp.dc._msdcs." + str(self.name) + " | cut -d ' ' -f 8"
        result = commands.getstatusoutput(cmd)
        wdcs = ''
        wdcslist = []
        if int(result[0]) == 0:
            lines = result[1].split("\n")
            for l in lines:
                val = l.strip()
                val = val.encode('ascii', 'ignore')
                # dc2 is currently offline --- 4/10/2018
                if 'dc2' not in val:
                    val = re.sub(".$", "", val)
                    wdcs = val + "," + wdcs
                    wdcslist.append(val)
        if wdcs != '':
            dcstr = re.sub(", $", "", wdcs)
            self.windcs = dcstr
            self.save()
        return wdcslist

    def get_ldap_domain_string(self):
        lds = ''
        dn = self.name.split(".")
        dn.reverse()
        for f in dn:
            lds = "DC=" + f + "," + lds
        lds = re.sub(",$", "", lds)
        return lds


#######################################
#   __        ___       ____   ____   #
#   \ \      / (_)_ __ |  _ \ / ___|  #
#    \ \ /\ / /| | '_ \| | | | |      #
#     \ V  V / | | | | | |_| | |___   #
#      \_/\_/  |_|_| |_|____/ \____|  #
#                                     #
#######################################

class WinDC(models.Model):
    name = models.CharField(max_length=256, null=True, default='unknownWinDCname')
    dnsdomain = models.ForeignKey(DNSdomain, null=True, default='0')
    orgs = models.TextField(default='')
    ipzones = models.TextField(default='')
    hosts = models.TextField(default='')
    ipzones_by_org = models.TextField(default='')
    hosts_by_ipzone = models.TextField(default='')
    ipzones_by_host = models.TextField(default='')
    updated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        msg = self.name
        return msg

    class Meta:
        verbose_name = "Windows DC"
        verbose_name_plural = "Windows DCs"

    def save(self, *args, **kwargs):
        # logger.debug("saving windc: " + str(self.name))
        super(WinDC, self).save(*args, **kwargs)

    def get_orgs(self):
        orglist = []
        orgs = str(self.orgs)
        for o in orgs.split(","):
            o = o.replace("u'", "'", 1000)
            o = re.sub("^\[", "", o)
            o = re.sub("\]$", "", o)
            if o != '':
                orglist.append(o)
        return orglist

    def set_orgs(self, olist):
        self.orgs = ''
        olist.sort()
        for o in olist:
            self.orgs = str(o) + "," + self.orgs
        self.orgs = re.sub(",$", "", o)
        self.save()

    def append_org(self, org):
        olist = self.get_orgs()
        olist.append(org)
        self.orgs = ''
        for o in olist:
            self.orgs = str(o) + "," + self.orgs
        self.orgs = re.sub(",$", "", self.orgs)
        self.save()

    def get_ipzones(self):
        zlist = []
        ipzones = str(self.ipzones)
        for z in ipzones.split(","):
            z = z.replace("u'", "'", 1000)
            z = re.sub("^\[", "", z)
            z = re.sub("\]$", "", z)
            if z != '':
                zlist.append(z)
        return zlist

    def set_ipzones(self, zlist):
        ipzones = ''
        zlist.sort()
        for z in zlist:
            ipzones = str(z) + "," + ipzones
        self.ipzones = re.sub(",$", "", ipzones)
        self.save()

    def append_ipzone(self, zone):
        ipzlist = self.get_ipzones()
        ipzlist.append(zone)
        self.ipzones = ''
        ipzlist.sort()
        for z in ipzlist:
            self.ipzones = str(z) + "," + self.ipzones
        self.ipzones = re.sub(",$", "", self.ipzones)
        self.save()

    def get_hosts(self):
        hlist = []
        hosts = str(self.hosts)
        for h in hosts.split(","):
            h = h.replace("u'", "'", 1000)
            h = re.sub("^\[", "", h)
            h = re.sub("\]$", "", h)
            if h != '':
                hlist.append(h)
        return hlist

    def set_hosts(self, hlist):
        self.hosts = ''
        hlist.sort()
        for h in hlist:
            if str(h) != '0.0.0.0':
                self.hosts = str(h) + "," + self.hosts
        self.hosts = re.sub(",$", "", self.hosts)
        self.save()

    def append_host(self, host):
        hostlist = self.get_hosts()
        hostlist.append(host)
        self.hosts = ''
        hostlist.sort()
        for h in hostlist:
            self.hosts = str(h) + "," + self.hosts
        self.hosts = re.sub(",$", "", self.hosts)
        self.save()

    def get_ipzones_by_org(self):
        ipzlist = []
        ipzbo = str(self.ipzones_by_org)
        for z in ipzbo.split(","):
            z = z.replace("u'", "'", 1000)
            z = re.sub("^\[", "", z)
            z = re.sub("\]$", "", z)
            if z != '':
                ipzlist.append(z)
        if len(ipzlist) > 1:
            ipzlist.sort
        return ipzlist

    def get_hosts_by_ipzone(self):
        hbz = self.hosts_by_ipzone
        if len(hbz) > 0:
            hbz = ast.literal_eval(hbz)
        else:
            hbz = {}
        return hbz

    def get_orgname_by_zone(self, ipz):
        ipz = str(ipz)
        orgname = 'unknown'
        qs = IPzone.objects.filter(name=ipz)
        if qs.count() > 0:
            orgname = str(qs[0].organization)
        else:
            orgname = ipz.split("/")
            orgname = orgname[0]
        return orgname

    def load_neworgs(self, src_cluster):
        oe = OrganizationExcludes()
        org_excludes = str(oe.get_excludes())
        ldorgs = self.get_orgs_from_ldap()
        orglist = self.get_orgs()
        neworgsset = set(ldorgs).symmetric_difference(orglist)
        neworgs = []
        for o in neworgsset:
            neworgs.append(o)
        state = False

        creator_msg = "load_neworgs"
        if len(neworgs) > 0:
            for oid in range(0, len(neworgs)):
                orgname = str(neworgs[oid].strip()).lower()
                orgname = orgname.replace(" ", "_", 100)
                msg = "   orgname is " + str(orgname) + " for oid " + str(oid)
                #logger.debug(msg)
                try:
                    quotasize = settings.ORGANIZATION_QUOTA_LIMITS[orgname]
                    units = 'tb'
                except:
                    quotasize = settings.DEFAULT_ORG_SMALL_QUOTA_LIMIT
                    units = 'gb'

                nextid = -1 * (Clusterpath.objects.all().count() + 1)
                testname = str(orgname) + " "
                if not testname in org_excludes:
                    state = True
                    # qname = "A_Quota_placeholder_" + str(orgname)
                    # qnames names must end with '/' to match the API responses
                    qname = settings.QUMULO_BASE_PATH + "/" + str(orgname).strip() + "/"
                    q = Quota.objects.filter(name=qname)
                    if q.count() == 0:
                        # set the primary email address based on the organization
                        addr = email_from_orgname(orgname)
                        qid = -1 * (Quota.objects.all().count() + 1)
                        q = Quota(qid=qid, name=qname, size=quotasize, units=units, do_not_delete=True,
                                  creator=creator_msg, primary=addr)
                        q.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addQuota:" + str(qname) + ":" + creator_msg
                        logger.info(msg)
                        q.set_pctusage()
                    else:
                        q = q[0]

                    cname = src_cluster.name
                    msg = " cname is " + str(cname)
                    #logger.debug(msg)
                    c = Cluster.objects.filter(name=cname)
                    if c.count() == 0:
                        cname = "CLUSTER_placeholder_this_should_not_happen"
                        c = Cluster(name=cname, ipaddr='0.0.0.0', adminpassword="notused")
                        c.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addCluster:" + str(cname) + ":" + creator_msg
                        logger.info(msg)
                    else:
                        c = c[0]

                    # cpname = "A_Clusterpath_placeholder_" + str(orgname)
                    # cp names must end with '/' to match the API responses
                    cpname = settings.QUMULO_BASE_PATH + "/" + str(orgname).strip() + "/"
                    # msg = "  cpname is " + str(cpname)
                    # logger.debug(msg)
                    # msg = "  cpname is " + str(cpname) + " and src_cluster.id is " + str(src_cluster)
                    #logger.debug(msg)
                    cp = Clusterpath.objects.filter(dirpath=cpname, cluster=src_cluster)
                    if cp.count() == 0:
                        msg = "  cp.count == 0, nextid = " + str(nextid) + " for cpname " + str(cpname)
                        # logger.debug(msg)
                        cp = Clusterpath(dirid=nextid, dirpath=cpname, cluster=c, quota=q, do_not_delete=True,
                                         creator=creator_msg)
                        cp.save(create_on_cluster=True)
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addClusterpath:" + str(cpname) + ":" + creator_msg
                        logger.info(msg)
                    else:
                        cp = cp[0]
                        msg = "  cp is " + str(cp)
                        #logger.debug(msg)

                    org = Organization.objects.filter(name=orgname)
                    if org.count() == 0:
                        thisorg = Organization(name=orgname)
                        thisorg.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addOrganization:" + str(orgname) + ":" + creator_msg
                        logger.info(msg)
                        thisorg.set_clusterpaths([cp])
                        try:
                            hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS[str(thisorg)]
                        except:
                            hostlist = settings.ORGANIZATION_DEFAULT_ADMIN_HOSTS['default']
                        thisorg.set_adminhosts(hostlist)
                    else:
                        thisorg = org[0]
                    cp.set_organization(thisorg)
                    q.set_organization(thisorg)
                    self.append_org(orgname)

                    # Default Report for all orgs -- just to test the GUI
                    rpt = Report(name=str(thisorg), type="gui test", cadence=30, units='d', creator=creator_msg )
                    rpt.save()
                    rpt.set_organization(thisorg)
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addReport:" + str(rpt.name) + ":" + creator_msg
                    logger.info(msg)

                #   testname in org_excludes
                # else:
                #    msg = " in load_neworgs( " + str(src_cluster) + ") ... skipping orgname >" + str(
                #        orgname) + "< found in organizational_excludes"
                #    logger.debug(msg)
        return state

    def load_newipzones(self):
        '''     '''
        ipzones_by_org = self.get_ipzones_by_org_from_ldap()
        zonehash = {}
        for o in ipzones_by_org.keys():
            for z in ipzones_by_org[o]:
                zonehash[z] = 1
        ldipzones = zonehash.keys()

        creator_msg = "load_newipzones"
        state = False
        if len(ldipzones) > 0:
            zonehash = {}
            for z in ldipzones:
                zonehash[z] = 1
                if "/" in str(z):
                    org = z.split("/")
                else:
                    org = z.split("-")
                org = org[0]
                oqs = Organization.objects.filter(name=org)
                if oqs.count() != 1:
                    msg = "error fetching org " + str(org)
                    logger.critical(msg)
                    sys.exit(-1)

                qs = IPzone.objects.filter(name=z)
                if qs.count() == 0:
                    # qname = "A_quota_placeholder_" + str(org)
                    # qnames names must end with '/' to match the API responses
                    qname = settings.QUMULO_BASE_PATH + "/" + str(org) + "/"
                    qr = Quota.objects.filter(name=qname)
                    if qr.count() == 0:
                        # set the primary email address based on the organization
                        addr = email_from_orgname(org)
                        qid = -1 * (Quota.objects.all().count() + 1)
                        q = Quota(qid=qid, name=qname, size=100, do_not_delete=True, creator=creator_msg,
                                  primary=addr)
                        q.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addQuota:" + str(qname) + ":" + creator_msg
                        logger.info(msg)
                        q.set_pctusage()
                    else:
                        q = qr[0]
                    q.set_organization(oqs[0])
                    nz = IPzone(name=z, organization=oqs[0], creator=creator_msg)
                    nz.save(new_host=True)
                    nz.set_ipzone_marker()
                    thisipzmarker = nz.get_ipzone_marker()
                    ipaddrs = []
                    ipaddrs.append(str(thisipzmarker).strip().encode('ascii', 'ignore'))
                    nz.set_ipaddrs(ipaddrs)
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addIPzone:" + str(z) + ":" + creator_msg
                    logger.info(msg)
                else:
                    if qs.count() != 1:
                        msg = "found multiple IPzones for name " + str(z)
                        logger.critical(msg)
                        sys.exit(-1)

            ipzones = ''
            for z in zonehash.keys():
                ipzones = z + "," + ipzones
            self.ipzones = re.sub(",$", "", ipzones)
            self.ipzones_by_org = str(ipzones_by_org)
            self.save()
            state = True
        return state

    def load_newhosts(self):

        state = False
        ldhosts = []
        zonesbyhost = {}
        hosts_by_zone = self.get_hosts_by_ipzone_from_ldap()
        for ipz in hosts_by_zone.keys():
            hostsinzone = hosts_by_zone[ipz]
            for h in hostsinzone:
                if settings.PRIVATE_ZONE_STR in str(ipz):
                    h = str(h).split('.')
                    h = h[0] + settings.PRIVATE_TLD
                ldhosts.append(h)
                try:
                    test = zonesbyhost[h]
                except:
                    zonesbyhost[h] = []
                zonesbyhost[h].append(ipz)
        hosts = self.get_hosts()

        newhostsset = set(ldhosts).difference(hosts)
        newhosts = []
        for h in newhostsset:
            newhosts.append(h)

        newhosts = ldhosts

        numhosts = len(newhosts)
        hn = int(1)
        if len(newhosts) > 0:
            nextid = -1 * (Clusterpath.objects.all().count())
            hosthash = {}
            for h in newhosts:
                creator_msg = "load_newhosts_" + str(hn) + "_of_" + str(numhosts)
                hn = hn + int(1)
                zones = zonesbyhost[h]
                for z in zones:
                    nextid = -1 * (nextid + 1)
                    orgname = self.get_orgname_by_zone(ipz=z)
                    org = Organization.objects.filter(name=orgname)
                    if org.count() == 0:
                        org = Organization(name=orgname)
                        org.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addOrganization:" + str(orgname) + ":" + creator_msg
                        logger.info(msg)
                    else:
                        org = org[0]
                    ipz = IPzone.objects.filter(name=z)
                    if ipz.count() == 0:
                        ipz = IPzone(name=z, organization=org, creator=creator_msg)
                        ipz.save(new_host=True)
                        ipz.set_ipzone_marker()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addIPzone:" + str(z) + ":" + creator_msg
                        logger.info(msg)
                    else:
                        ipz = ipz[0]
                    host = Host.objects.filter(name=h)
                    if host.count() == 0:
                        host = Host(name=h, ipzone=ipz, organization=org)
                        host.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addHost:" + str(h) + ":" + creator_msg
                        logger.info(msg)
                    else:
                        host = host[0]
                    host.check_hostip()
                    hosthash[h] = 1
                    state = True
                    ipaddrs = set(ipz.get_ipaddrs())
                    myip = host.getip()
                    ipaddrs.add(str(myip).strip().encode('ascii', 'ignore'))
                    thisipzmarker = ipz.get_ipzone_marker()
                    thisipzmarker = str(thisipzmarker).strip().encode('ascii', 'ignore')
                    ipaddrs.add(thisipzmarker)
                    ipz.set_ipaddrs(ipaddrs, new_host=True)
                    ipz.save(new_host=True)

            if state is True:
                self.hosts = ''
                for h in hosthash.keys():
                    h = str(h).strip().encode('ascii', 'ignore')
                    if h != '0.0.0.0':
                        self.hosts = h + "," + self.hosts
                self.hosts = re.sub(",$", "", self.hosts)
                self.hosts_by_ipzone = str(hosts_by_zone)

                ipzones_by_host = {}
                for z in hosts_by_zone.keys():
                    for h in hosts_by_zone[z]:
                        try:
                            test = ipzones_by_host[h]
                        except:
                            ipzones_by_host[h] = []
                        ipzones_by_host[h].append(z)
                self.ipzones_by_host = str(ipzones_by_host)
                self.save()
                self.sync_ips_in_ipzones()
        return state

    def get_orgs_from_ldap(self):
        domain = DNSdomain.objects.filter(name=self.dnsdomain).first()
        lds = str(domain.get_ldap_domain_string())
        cmd = "/usr/bin/ldapsearch -x -D ldap2ad -y /qumuloadmin/qrba_admin/config/ADcred -H ldaps://" + str(
            self.name) + ":636 -s one -b '" + lds + "' '(objectClass=organizationalUnit)' ou | grep '^ou:'"
        #print("cmd: " + str(cmd) + "\n\n")

        result = commands.getstatusoutput(cmd)
        # print("result: " + str(result))
        oe = OrganizationExcludes()
        org_excludes = str(oe.get_excludes())
        orgset = set()
        if int(result[0]) == 0:
            lines = result[1].split("\n")
            for l in lines:
                l = l.split(":")
                # add trailing a space to insure 'SOMESTRING' is not removed by the 'SOMESTRINGTest' entry
                o = l[1].strip() + " "
                if o not in org_excludes:
                    orgset.add(o)
                # else:
                #    msg = "found " + str(o) + " in " + str(org_excludes)
                #    logger.debug(msg)

            # never entered into ADcontrollers
            orgset.add("ATEST")
            orgset.add("TEST2")

        orgs = []
        for o in orgset:
            orgs.append(o)
        orgs.sort()
        # msg = "org: " + str(orgs)
        # logger.debug(msg)
        return orgs

    def get_ipzones_by_org_from_ldap(self):
        ipzones_by_org = {}
        domain = DNSdomain.objects.filter( name=self.dnsdomain ).first()
        lds = str(domain.get_ldap_domain_string())
        orgs = []
        allorgs = Organization.objects.all()
        for o in allorgs:
            orgs.append(o.name)
        for o in orgs:
            cmd = "/usr/bin/ldapsearch -x -D ldap2ad -y /qumuloadmin/qrba_admin/config/ADcred -H ldaps://" + str(
                self.name) + ":636 -s one -b 'OU=Zones,OU=UNIX,OU=" + str(
                o) + "," + lds + "' '(objectClass=organizationalUnit)' ou | grep '^ou:'"
            #print( cmd )
            result = commands.getstatusoutput(cmd)
            if int(result[0]) == 0:
                try:
                    test = ipzones_by_org[o]
                except:
                    ipzones_by_org[o] = []
                lines = result[1].split("\n")
                for l in lines:
                    l = l.split(":")
                    # ipz = str(self.dnsdomain) + "/" + str(o) + "/UNIX/Zones/" + str(l[1].strip())
                    ipz = str(o) + "/" + str(l[1].strip())
                    ipzones_by_org[o].append(ipz)
        return ipzones_by_org

    def get_hosts_by_ipzone_from_ldap(self):
        domain = DNSdomain.objects.filter(name=self.dnsdomain).first()
        lds = str(domain.get_ldap_domain_string())
        hosts_by_ipzone = {}
        ipzones_by_org = self.get_ipzones_by_org_from_ldap()
        orgs = ipzones_by_org.keys()
        for org in orgs:
            for ipz in ipzones_by_org[org]:
                try:
                    test = hosts_by_ipzone[ipz]
                except:
                    hosts_by_ipzone[ipz] = []
                ou = str(ipz)
                ou = ou.split("/")
                ou = ou[len(ou) - 1]
                cmd = "/usr/bin/ldapsearch -x -D ldap2ad -y /qumuloadmin/qrba_admin/config/ADcred -H ldaps://" + str(
                    self.name) + ":636 -s one -b 'cn=Computers,OU=" + ou + ",OU=Zones,OU=UNIX,OU=" + org + "," + lds + "' '(objectClass=leaf)' name | grep '^name:'"
                result = commands.getstatusoutput(cmd)
                msg = "   result = " + str(result)
                # logger.debug(msg)
                if int(result[0]) == 0:
                    lines = result[1].split("\n")
                    msg = "   found " + str(len(lines)) + " hosts for org " + str(org) + " and adzone " + str(ipz)
                    # logger.debug(msg)
                    for l in lines:
                        l = l.split(":")
                        hostname = l[1].strip().encode('ascii', 'ignore')
                        msg = "    hostname: " + str(hostname)
                        # logger.debug(msg)
                        try:
                            dnsipaddress = socket.gethostbyname(hostname)
                            hosts_by_ipzone[ipz].append(hostname)
                            msg = "    hosts_by_ipzone[" + str(ipz) + "] = " + str(hosts_by_ipzone[ipz])
                            # logger.debug(msg)
                        except socket.error:
                            pass
                else:
                    msg = " none-zero result for org " + str(org) + " and adzone " + str(ipz)
                    #logger.debug(msg)
                    msg = "       result: " + str(result)
                    #logger.debug(msg)
                msg = "    number of hosts_by_ipzone[ " + str(ipz) + " ]: " + str(len(hosts_by_ipzone[ipz]))
                # logger.debug(msg)
                if len(hosts_by_ipzone[ipz]) > 0:
                    msg = "              hosts_by_ipzone[ " + str(ipz) + " ]: " + str(hosts_by_ipzone[ipz]) + "\n"
                    #logger.debug(msg)

        return hosts_by_ipzone

    def get_hosts_by_org_from_ldap(self):
        domain = DNSdomain.objects.filter(name=self.dnsdomain).first()
        lds = str(domain.get_ldap_domain_string())
        hosts_by_org = {}
        hosts_by_ipzone = {}
        ipzones_by_org = self.get_ipzones_by_org_from_ldap()
        orgs = ipzones_by_org.keys()
        for org in orgs:
            try:
                test = hosts_by_org[org]
            except:
                hosts_by_org[org] = []
            for ipz in ipzones_by_org[org]:
                try:
                    test = hosts_by_ipzone[ipz]
                except:
                    hosts_by_ipzone[ipz] = []
                ou = str(ipz)
                ou = ou.split("/")
                ou = ou[len(ou) - 1]
                cmd = "/usr/bin/ldapsearch -x -D ldap2ad -y /qumuloadmin/qrba_admin/config/ADcred -H ldaps://" + str(
                    self.name) + ":636 -s one -b 'cn=Computers,OU=" + ou + ",OU=Zones,OU=UNIX,OU=" + org + "," + lds + "' '(objectClass=leaf)' name | grep '^name:'"
                result = commands.getstatusoutput(cmd)
                msg = "   result = " + str(result)
                #logger.debug(msg)
                if int(result[0]) == 0:
                    lines = result[1].split("\n")
                    msg = "   found " + str(len(lines)) + " hosts for org " + str(org) + " and adzone " + str(ipz)
                    #logger.debug(msg)
                    for l in lines:
                        l = l.split(":")
                        hostname = l[1].strip().encode('ascii','ignore')
                        msg = "    hostname: " + str(hostname)
                        # logger.debug(msg)
                        try:
                            dnsipaddress = socket.gethostbyname(hostname)
                            hosts_by_ipzone[ipz].append(hostname)
                            hosts_by_org[org].append(hostname)
                        except socket.error:
                            pass
                else:
                    msg = " none-zero result for org " + str(org) + " and adzone " + str(ipz)
                    # logger.debug(msg)
                    msg = "       result: " + str(result)
                    #logger.debug(msg)
                msg = "    number of hosts_by_ipzone[ " + str(ipz) + " ]: " + str(len(hosts_by_ipzone[ipz]))
                # logger.debug(msg)
                # if len(hosts_by_ipzone[ipz]) > 0:
                # msg = "              hosts_by_ipzone[ " + str(ipz) + " ]: " + str(hosts_by_ipzone[ipz]) + "\n"
                # logger.debug(msg)

        return hosts_by_org

    def sync_ips_in_all_WinDCs(self):
        activity_by_windc = {}
        windc = WinDC.objects.all()
        for dc in windc:
            activity_by_windc[dc] = dc.sync_ips_in_ipzones()
        return activity_by_windc

    def sync_ips_in_ipzones(self):
        activity = {}
        hosts_by_zone = self.get_hosts_by_ipzone()
        for z in hosts_by_zone.keys():
            ips = []
            for h in hosts_by_zone[z]:
                thishost = Host.objects.filter(name=h)
                if thishost.count() == 1:
                    ips.append(thishost[0].ipaddr)
            ipz = IPzone.objects.filter(name=z)
            if ipz.count() == 1:
                ipz = ipz[0]
                # ipz.set_immutable(False)
                if not ipz.is_immutable():
                    ipz.set_ipaddrs(ips)
                else:
                    msg = "   ipz " + str(ipz) + " is immutable"
                    #logger.debug(msg)
                ipz.set_immutable(True)
                activity[z] = str(len(ips))
        if len(hosts_by_zone) > 0:
            self.save()
        return activity


#########################################################
#    ____           _        _      _   _               #
#   |  _ \ ___  ___| |_ _ __(_) ___| |_(_) ___  _ __    #
#   | |_) / _ \/ __| __| '__| |/ __| __| |/ _ \| '_ \   #
#   |  _ <  __/\__ \ |_| |  | | (__| |_| | (_) | | | |  #
#   |_| \_\___||___/\__|_|  |_|\___|\__|_|\___/|_| |_|  #
#                                                       #
#########################################################

class Restriction(models.Model):
    name = models.CharField(max_length=150, help_text="Name of this NFS Restriction")
    ipzones = models.ManyToManyField(IPzone, related_name='restriction_ipzone', verbose_name="IP Zones",
                                     default=settings.NONE_NAME, help_text="One or more IP Zones are REQUIRED")
    readonly = models.BooleanField(verbose_name="Read Only:", help_text=settings.HELP_TEXT_RESTRICTION_READONLY)
    usermapping = models.CharField('User Mapping:', max_length=150, choices=UM_CHOICES, default='None',
                                   help_text=settings.HELP_TEXT_NFSEXPORT_USERMAPPING)
    usermapid = models.IntegerField(default=0, help_text=settings.HELP_TEXT_NFSEXPORT_USERMAPID)
    individual_hosts = models.ManyToManyField(Host, default=settings.NONE_NAME,
                                              help_text=settings.HELP_TEXT_RESTRICTION_INDIVIDUAL_HOSTS)
    organization = models.ForeignKey('provision.Organization', related_name='restriction_org', null=True,
                                     help_text=settings.HELP_TEXT_ORGANIZATION)
    do_not_delete = models.BooleanField(default=False, help_text=settings.HELP_TEXT_DND)
    creator = models.CharField(default='unknown', max_length=200)
    updater = models.CharField(default='None', max_length=200)
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('id',)
        verbose_name = "NFS Restriction"
        verbose_name_plural = "NFS Restrictions"

    def __str__(self):
        return self.name

    def get_do_not_delete(self):
        return self.do_not_delete

    def save(self, *args, **kwargs):
        msg = "   in restriction save -- self is " + str(self)
        #logger.info(msg)

        thisumapping = convert_nfs_user_mapping(self.usermapping)
        if thisumapping != self.usermapping:
            self.usermapping = thisumapping
        super(Restriction, self).save(*args, **kwargs)
        # now = datetime.datetime.utcnow()
        # msg = str(now) + ":superRestriction:" + str(self.name) + ":" + self.get_updater()
        #logger.info(msg)

        # Locate and save (update) associated NSF exports
        # collect parents as a set since theoretically a restriction could be used by more than one export
        # note: this code is necessarily repeated in post_save_restriction()
        nsfparents = set()
        for x in NfsExport.objects.all():
            xrqs = x.get_restrictions()
            for xr in xrqs:
                if xr == self:
                    nsfparents.add(x)

        for x in nsfparents:
            now = datetime.datetime.utcnow()
            msg = str(now) + ":saving nfsexport " + str(x) + " for restriction:" + str(self) + ":" + self.get_updater()
            #logger.info(msg)
            x.save(update_on_cluster=True)

    def get_ipzones(self):
        return self.ipzones.get_queryset()

    def get_individual_hosts(self):
        return self.individual_hosts.get_queryset()

    def get_creator(self):
        return str(self.creator)

    def get_updater(self):
        return str(self.updater)

    def set_updater(self, who):
        self.updater = who
        self.save()

    def get_all_ipzone_ipaddrs(self):
        ''' returns a list of all ip addresses associated with this Restriction '''
        ipaddrsset = set()
        ipzones = self.get_ipzones()
        for z in ipzones:
            for ip in z.get_ipaddrs():
                ipaddrsset.add(str(ip).strip().encode('ascii', 'ignore'))
        ipaddrs = []
        for ip in ipaddrsset:
            ipaddrs.append(ip)
        if len(ipaddrs) > 1:
            ipaddrs.sort()
        return ipaddrs

    def set_default_ipzone_ipaddrs(self, iplist):
        ''' sets the ipaddrs of the default IPZone to the given iplist '''
        ipzone = self.get_ipzones()
        if len(ipzone) > 0:
            ipzone = ipzone[0]
            tlist = []
            for ip in iplist:
                ip = str(ip).strip().encode('ascii', 'ignore')
                if ip != '0.0.0.0' and ip != '':
                    tlist.append(ip)
            tlist.sort()
            ipzone.set_ipaddrs(tlist)
            self.save()

    def set_ipzone_ipaddrs(self, ipzonename, iplist):
        ''' sets the ipaddrs of the given IPZone to the given iplist '''
        qs = IPzone.objects.filter(name=ipzonename)
        if qs.count() > 0:
            ipzone = qs[0]
            tlist = []
            for ip in iplist:
                ip = str(ip).strip().encode('ascii', 'ignore')
                if ip != '0.0.0.0' and ip != '':
                    tlist.append(ip)
            tlist.sort()
            ipzone.set_ipaddrs(tlist)
            self.save()

    def get_all_individual_ipaddrs(self):
        ''' returns a list of all individual hosts ip addresses associated with this Restriction '''
        allips = {}
        for ih in self.get_individual_hosts():
            allips[ih.getip()] = 1
        ipaddrs = []
        ipset = set()
        for ip in allips.keys():
            ipset.add(ip)
        for ip in ipset:
            if ip != '0.0.0.0' and ip != '':
                ipaddrs.append(str(ip).strip().encode('ascii', 'ignore'))
        ipaddrs.sort()
        return ipaddrs

    def set_organization(self, org):
        self.organization = org
        self.save()

    def delete(self, using=None, keep_parents=False):
        now = datetime.datetime.utcnow()
        if self.get_do_not_delete() is False:
            self.delete_from_cluster()
            super(Restriction, self).delete(using=using, keep_parents=keep_parents)
            msg = str(now) + ":deleteRestriction:" + str(self.name) + ":" + self.get_updater()
        else:
            msg = str(now) + ":attempted_deleteRestriction:" + str(self.name) + ":" + self.get_updater()
        logger.info(msg)

    def delete_from_cluster(self):
        now = datetime.datetime.utcnow()
        msg = str(now)
        if self.get_do_not_delete() is False:
            nsfxparents = set()
            for x in NfsExport.objects.all():
                xrqs = x.restrictions.get_queryset()
                for xr in xrqs:
                    if xr == self:
                        nsfxparents.add(x)
            if len(nsfxparents) > 0:
                for x in nsfxparents:
                    x.delete()
                msg = msg + ":deleteRestrictionFromCluster_deletedNsfxparents:" + str(
                    nsfxparents)
            else:
                msg = msg + ":deleteRestrictionFromCluster_no_nsfxparents:"
        else:
            msg = msg + ":attempted_deleteRestrictionFromCluster:" + str(self.name)
        msg = msg + ":" + self.get_updater()
        logger.info(msg)

######################################################
#    _   _  __     _____                       _     #
#   | \ | |/ _|___| ____|_  ___ __   ___  _ __| |_   #
#   |  \| | |_/ __|  _| \ \/ / '_ \ / _ \| '__| __|  #
#   | |\  |  _\__ \ |___ >  <| |_) | (_) | |  | |_   #
#   |_| \_|_| |___/_____/_/\_\ .__/ \___/|_|   \__|  #
#                            |_|                     #
######################################################

class NfsExport(models.Model):
    exportpath = models.CharField("Export Name:", default="/", max_length=255,
                                  help_text=settings.HELP_TEXT_NFSEXPORTPATH)
    description = models.CharField(max_length=255, default='none', help_text=settings.HELP_TEXT_NFSEXPORTDESC)
    restrictions = models.ManyToManyField(Restriction, verbose_name="NFS Restrictions",
                                          help_text=settings.HELP_TEXT_NFSEXPORTREST)
    clusterpath = models.ForeignKey(Clusterpath, on_delete=models.CASCADE,
                                    help_text=settings.HELP_TEXT_NFSEXPORT_CLUSTERPATH, null=True)
    create_subdirs = models.BooleanField(verbose_name="Create a sub-clusterpath?", default=False,
                                         help_text=settings.HELP_TEXT_NFSEXPORT_CREATE_SUBDIRS)
    exportid = models.IntegerField(default=0)
    organization = models.ForeignKey(Organization, null=True,
                                     related_name='nfsexport_org', help_text=settings.HELP_TEXT_ORGANIZATION)
    do_not_delete = models.BooleanField(default=False, help_text=settings.HELP_TEXT_DND)
    creator = models.CharField(default='unknown', max_length=200)
    updater = models.CharField(default='None', max_length=200)
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('id',)
        verbose_name = "NFS Export"
        verbose_name_plural = "NFS Exports"

    def __str__(self):
        return self.exportpath

    def get_do_not_delete(self):
        return self.do_not_delete

    def get_clusterpath(self):
        return self.clusterpath

    def get_creator(self):
        return str(self.creator)

    def get_updater(self):
        return str(self.updater)

    def contact(self):
        return str(self.creator)

    def set_updater(self, who):
        self.updater = who
        self.save()

    def get_restrictions(self):
        return self.restrictions.get_queryset()

    def save(self, create_on_cluster=False, update_on_cluster=False, do_not_delete=False, *args, **kwargs):
        super(NfsExport, self).save(*args, **kwargs)

        # now = datetime.datetime.utcnow()
        #msg = str(now) + ":super1NfsExport:" + str(self.exportpath) + ":" + self.get_updater()
        #logger.info(msg)

        mycluster = self.clusterpath.cluster
        # msg = "\nsaving nfsexport: " + str(self) + " -- id = " + str(self.id) + ", xid = " + str(
        #    self.exportid) + ", xp = " + str(self.exportpath) + ", mycluster is " + str(
        #    mycluster) + ", clusterpath is " + str(self.clusterpath)
        #logger.info(msg)
        # logger.debug(msg)
        #msg = "      coc = " + str(create_on_cluster) + ", upc = " + str(update_on_cluster)
        #logger.debug(msg)

        exportid = int(self.exportid)
        #msg = "    exportid is " + str(exportid)
        #logger.debug(msg)

        if exportid < 1:
            create_on_cluster = True
            msg = "    exportid < 1 -- con = " + str(create_on_cluster)
            #logger.debug(msg)
        else:
            update_on_cluster = True
        msg = "      coc2 = " + str(create_on_cluster) + ", upc = " + str(update_on_cluster)
        #logger.debug(msg)

        exportpath = str(self.exportpath)
        # enforce leading "/" as required by qumulo api
        if exportpath[0:1] != "/":
            exportpath = "/" + exportpath
        # remove any trailing '/' -- but only if this is not the true mount point '/'
        if exportpath != '/':
            exportpath = re.sub("/$", "", exportpath)

        exportpath = exportpath.encode('ascii', 'ignore')
        self.exportpath = exportpath
        msg = "        self.exportpath = " + str(self.exportpath)
        #logger.debug(msg)
        msg = "               exportid =" + str(exportid) + " -- create_on_cluster = " + str(create_on_cluster)
        #logger.debug(msg)

        fspath = str(self.clusterpath.dirpath).encode('ascii', 'ignore')
        fspath = fspath.replace('\n', '')
        # If this is a root clusterpath then add the export path
        if self.create_subdirs is True:
            fspath = fspath + exportpath
        fspath = fspath.replace("//", "/", 100)
        if fspath != '/':
            if settings.QUMULO_BASE_PATH not in fspath:
                fspath = settings.QUMULO_BASE_PATH + "/" + fspath

        # enforce trailing '/' on fspath
        if fspath[len(fspath) - 1:len(fspath)] != '/':
            fspath = fspath + "/"
        msg = " fspath is " + str(fspath)
        #logger.debug(msg)

        description = str(self.description)
        description = description.encode('ascii', 'ignore')
        # super(NfsExport, self).save(*args, **kwargs)
        # now = datetime.datetime.utcnow()
        #msg = str(now) + ":super2NfsExport:" + str(self.exportpath) + ":" + self.get_updater()
        #logger.info(msg)

        rlist = []
        clusterexportid = -1
        if create_on_cluster is True or update_on_cluster is True:
            shares = mycluster.fetch_nfs_shares(mycluster)
            msg = "         found " + str(len(shares)) + " nfs_shares"
            #logger.debug(msg)
            foundshare = ""
            for s in shares:
                # unicode to str to make the == work
                ep = str(s['export_path']).encode('ascii', 'ignore')
                if exportpath == ep:
                    foundshare = s
                    clusterexportid = str(s['id']).encode('ascii', 'ignore')
                    create_on_cluster = False
                    update_on_cluster = True
                    msg = "      now coc = " + str(create_on_cluster) + ", upc = " + str(update_on_cluster)
                    #logger.debug(msg)
                    msg = "      breaking on s = " + str(foundshare) + " for ep " + str(ep)
                    #logger.debug(msg)
                    break

            allr = self.get_restrictions()
            msg = "   allr is " + str(allr) + "\n"
            #logger.info(msg)
            for r in allr:
                newr = NFSRestriction.create_default()
                #        return cls({'read_only': False, 'host_restrictions': [],
                #         'user_mapping': 'NFS_MAP_NONE', 'map_to_user_id': '0'})
                newr['read_only'] = r.readonly
                newr['user_mapping'] = convert_nfs_user_mapping(r.usermapping).encode('ascii', 'ignore')
                newr['map_to_user_id'] = str(r.usermapid)
                newr['host_restrictions'] = []
                ipzones = r.get_ipzones()
                msg = "     ipzones are: " + str(ipzones)
                #logger.debug(msg)
                hostset = set()
                ipzmarkersset = set()
                for z in ipzones:
                    ipzmarkersset.add(z.get_ipzone_marker())
                    for h in z.get_ipaddrs():
                        h = str(h).encode('ascii', 'ignore').strip()
                        h = h.replace(",", "")
                        if h != '0.0.0.0' and h != '' and h != settings.LOCALHOST:
                            # newr['host_restrictions'].append(h)
                            hostset.add(h)
                for h in r.get_all_individual_ipaddrs():
                    hostset.add(h)
                for ip in ipzmarkersset:
                    hostset.add(ip)
                for h in hostset:
                    newr['host_restrictions'].append(h)
                if len(newr['host_restrictions']) > 0:
                    rlist.append(newr)

            if len(rlist) == 0:
                create_on_cluster = False
                update_on_cluster = False
                msg = "          len(rlist) = " + str(len(rlist))
            else:
                msg = "            rlist: " + str(rlist)
            #logger.debug(msg)


        org = self.clusterpath.organization
        self.clusterpath.quota.set_organization(org)
        if self.organization != org:
            self.organization = org
            super(NfsExport, self).save(*args, **kwargs)
            # now = datetime.datetime.utcnow()
            # msg = str(now) + ":super3NfsExport:" + str(self.exportpath) + ":" + self.get_updater()
            #logger.info(msg)
        msg = "          clusterexportid = " + str(clusterexportid)
        #logger.debug(msg)

        if create_on_cluster is True:
            msg = "       creating on cluster -- I am nfsexport " + str(
                self) + " -- exportid, exportpath, fspath: " + str(exportid) + ", " + str(exportpath) + ", " + str(
                fspath) + "\nrestrictions:\n" + str(rlist)
            #logger.info(msg)
            (conninfo, creds) = qlogin(self.clusterpath.cluster.ipaddr, self.clusterpath.cluster.adminname,
                                       self.clusterpath.cluster.adminpassword,
                                       self.clusterpath.cluster.port)
            try:
                qpi = qumulo.rest.nfs.nfs_add_export(conninfo, creds, exportpath, fspath, description,
                                                    rlist, allow_fs_path_create=True)
                msg = "   qpi: " + str(qpi)
                #logger.debug(msg)
                self.exportid = qpi.lookup('id')
                super(NfsExport, self).save(*args, **kwargs)
                now = datetime.datetime.utcnow()
                msg = str(now) + ":createdNfsExport:" + str(self.exportpath) + ":" + self.get_updater()
                logger.info(msg)
                now = datetime.datetime.utcnow()
                msg = str(now) + ":updating self.exportid to:" + str(self.exportid) + ":" + self.get_updater()
                #logger.info(msg)
            except qumulo.lib.request.RequestError as err:
                msg = "        RequestError: " + str(err) + " at nfs add share " + str(id) + " .... exiting now!"
                logger.critical(msg)
                sys.exit(-1)

            qname = fspath + "/"
            qname = qname.replace("//", "/")
            qs = Clusterpath.objects.filter(dirpath=qname)
            if qs.count() == 0:
                # create and associated directories and share on the cluster and a clusterpath in the system
                dirid = mycluster.create_directory_on_cluster(conninfo, creds, qname)
                msg = " dirid is " + str(dirid) + " for qname " + str(qname)
                # logger.debug(msg)
                if self.clusterpath.quota.name != settings.NONE_NAME:
                    msg = mycluster.create_quota_on_cluster(conninfo, creds, dirid, qname, self.clusterpath.quota.size)
                    #logger.debug(msg)
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":created_quota_on_cluster_qname:" + str(qname) + ":" + self.get_updater()
                    logger.info(msg)
                else:
                    # dirid = 0
                    msg = "    self.clusterpath.quota.name is NONE_NAME == " + str(settings.NONE_NAME)
                    #logger.debug(msg)

                msg = "    qname is " + str(qname)
                #logger.debug(msg)
                qs = Quota.objects.filter(name=qname)
                if qs.count() == 0:
                    mysize = int(math.floor((float((100 - settings.QUOTA_SAFETY_MARGIN_PERCENTAGE)) / 100.0 * float(
                        self.clusterpath.quota.size))))
                    myquota = Quota(name=qname, size=mysize, organization=self.organization,
                                    creator=self.creator)
                    myquota.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":newQuota:" + str(qname) + ":" + self.get_updater()
                    logger.info(msg)
                    myquota.set_pctusage()

                    # create a new clusterpath which will be removed from the cluster when its NFSexport is deleted
                    newcp = Clusterpath(dirid=dirid, dirpath=qname, cluster=mycluster, quota=myquota,
                                    organization=self.clusterpath.organization, do_not_delete=False)
                    newcp.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":newClusterpath:" + str(qname) + ":" + self.get_updater()
                    logger.info(msg)
                    # make it the new clusterpath
                    if self.create_subdirs is True:
                        self.clusterpath = newcp
                        self.create_subdirs = False
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":newCreate_sudirs:" + str(self.create_subdirs) + ":" + self.get_updater()
                        logger.info(msg)
                # else:
                #    myquota = qs[0]

                super(NfsExport, self).save(*args, **kwargs)
                # now = datetime.datetime.utcnow()
                #msg = str(now) + ":super5NfsExport:" + str(self.exportpath) + ":" + self.get_updater()
                #logger.info(msg)
            else:
                msg = "  qs.count() = " + str(qs.count()) + " for fspath " + str(fspath)
                #logger.debug(msg)

        if update_on_cluster is True:
            # msg = "       modifying -- I am nfsexport " + str(self) + " -- exportid, exportpath, fspath: " + str(
            #    exportid) + ", " + str(exportpath) + ", " + str(fspath) + "restrictions:" + str(rlist)
            #logger.info(msg)

            # Case that an export has been renamed... there will be no clustererport_id, but there will be a local exportid
            if int(clusterexportid) < 0 and int(exportid) > 0:
                msg = "    clusterexportid <0 === " + str(clusterexportid)
                logger.info(msg)
                clusterexportid = str(exportid)
                msg = "    clusterexportid now =  " + clusterexportid
                logger.info(msg)
            else:
                msg = "    clusterexporid < 0 === " + str(
                    clusterexportid) + ", and exportid <=0 ... exporid === " + str(exportid)
                logger.info(msg)
                logger.critical(msg)
                # sys.exit(-1)

            (conninfo, creds) = qlogin(self.clusterpath.cluster.ipaddr, self.clusterpath.cluster.adminname,
                                       self.clusterpath.cluster.adminpassword,
                                       self.clusterpath.cluster.port)
            try:
                qpi = qumulo.rest.nfs.nfs_modify_share(conninfo, creds, clusterexportid, exportpath, fspath, description,
                                                           rlist)
                msg = "   qpi: " + str(qpi)
                #logger.info(msg)
                now = datetime.datetime.utcnow()
                msg = str(now) + ":updated NfsExport self.exportid:" + str(clusterexportid) + ":" + self.get_updater()
                logger.info(msg)
            except qumulo.lib.request.RequestError as err:
                msg = "        RequestError: " + str(err) + " at nfs modify share " + str(id) + " exiting now!"
                logger.info(msg)
                # logger.critical(msg)
                #sys.exit(-1)

        msg = "   exiting nfs save for " + str(self)
        #logger.info(msg)
        msg = "           exportid = " + str(self.exportid) + " for exportpath " + str(exportpath) + "\n"
        #logger.debug(msg)


    def set_organization(self, org):
        self.organization = org
        self.save()

    def set_restrictions(self, newlist):
        ''' Replaces the existing list of Restrictions with newlist '''
        msg = "       I am NFSexport " + str(self)
        #logger.debug(msg)

        msg = "       new list: " + str(newlist)
        #logger.debug(msg)

        allr = self.restrictions.all()
        msg = "    allr is " + str(allr)
        #logger.debug(msg)

        for r in self.restrictions.all():
            r.delete()
            msg = "    deleted r " + str(r)
            #logger.debug(msg)
        self.save()

        for r in newlist:
            self.restrictions.add(r)
        self.save()

    def delete(self, using=None, keep_parents=False):
        msg = "    in delete nfsexport self = " + str(self)
        #logger.info(msg)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if self.get_do_not_delete() is False:
            self.delete_from_cluster()
            super(NfsExport, self).delete(using=using, keep_parents=keep_parents)
            msg = msg + ":deleteNfsExport:"
        else:
            msg = msg + ":attempted_deleteNfsExport:"
        msg = msg + str(self.exportpath) + ":" + self.get_updater()
        logger.info(msg)

    def delete_from_cluster(self):
        msg = "    in delete_from_cluster nfsexport self = " + str(self)
        #logger.info(msg)
        now = datetime.datetime.utcnow()
        if self.get_do_not_delete() is False:
            (conninfo, creds) = qlogin(self.clusterpath.cluster.ipaddr, self.clusterpath.cluster.adminname,
                                       self.clusterpath.cluster.adminpassword,
                                       self.clusterpath.cluster.port)
            if not conninfo:
                msg = "could not connect to cluster " + str(self.clusterpath.cluster.name) + "  ... exiting"
                logger.info(msg)
                logger.critical(msg)
                sys.exit(-1)

            msg = self.clusterpath.cluster.delete_nfsexport_on_cluster(conninfo, creds, xid=self.exportid)
            msg = "   deleted " + str(self.exportid) + " on " + str(self.clusterpath.cluster.name) + " --  msg = " + msg
            # logger.debug(msg)
            msg = str(now) + ":deleteNfsExportFromCluster:" + str(self.exportpath) + ":" + self.get_updater()
            logger.info(msg)

            now = datetime.datetime.utcnow()
            msg = str(now)
            if self.clusterpath.do_not_delete is False:
                msg = self.clusterpath.cluster.delete_quota_on_cluster(conninfo, creds, id=self.clusterpath.dirid,
                                                                       path=self.clusterpath.dirpath)
                # logger.debug(msg)
                msg = msg + ":deleteNfsExportFromCluster_deleteClusterpath:"
            else:
                msg = msg + ":attempted_deleteNfsExportFromCluster_Clusterpath:"
            msg = msg + str(self.clusterpath.dirpath) + ":" + self.clusterpath.get_updater()
            logger.info(msg)
        else:
            msg = "  self.do_not_delete is false for nfsexport " + str(self)
            #logger.debug(msg)
            msg = str(now) + ":attempted_deleteNfsExportFromCluster:" + str(self.exportpath) + ":" + self.get_updater()
            logger.info(msg)


######################################################
#    ____                      _           _         #
#   / ___| _   _ ___  __ _  __| |_ __ ___ (_)_ __    #
#   \___ \| | | / __|/ _` |/ _` | '_ ` _ \| | '_ \   #
#    ___) | |_| \__ \ (_| | (_| | | | | | | | | | |  #
#   |____/ \__, |___/\__,_|\__,_|_| |_| |_|_|_| |_|  #
#          |___/                                     #
######################################################

class Sysadmin(models.Model):
    name = models.CharField(max_length=100, null=True, default='unknownSysadminname')
    organizations = models.ManyToManyField(Organization)
    organization = models.ForeignKey(Organization, null=True, related_name='sysadm_home_org',
                                     verbose_name='Primary Organization')
    is_a_superuser = models.BooleanField(default=False)
    updated = models.TimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # logger.debug("saving sysadm: " + str(self.name))
        super(Sysadmin, self).save(*args, **kwargs)

    def get_organizations(self):
        return self.organizations.get_queryset()

    def get_home_organization(self):
        return self.organization


##########################################################################
#    ____                  ___       ____        _                 _     #
#   |  _ \  __ _ _   _ ___|_ _|_ __ |  _ \  __ _| |_ __ _ ___  ___| |_   #
#   | | | |/ _` | | | / __|| || '_ \| | | |/ _` | __/ _` / __|/ _ \ __|  #
#   | |_| | (_| | |_| \__ \| || | | | |_| | (_| | || (_| \__ \  __/ |_   #
#   |____/ \__,_|\__, |___/___|_| |_|____/ \__,_|\__\__,_|___/\___|\__|  #
#                |___/                                                   #
##########################################################################

class DaysInDataset(models.Model):
    label = models.CharField(max_length=150, choices=DAYS_IN_DATASET)
    days = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Days in Dataset"
        verbose_name_plural = verbose_name

    def __str__(self):
        name = str(self.days)
        return name

    def get_label(self):
        return self.label

    def get_days(self):
        return self.days


#################################################################
#       _        _   _       _ _        _____                   #
#      / \   ___| |_(_)_   _(_) |_ _   |_   _|   _ _ __   ___   #
#     / _ \ / __| __| \ \ / / | __| | | || || | | | '_ \ / _ \  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| || || |_| | |_) |  __/  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, ||_| \__, | .__/ \___|  #
#                                  |___/     |___/|_|           #
#################################################################

class ActivityType(models.Model):
    activitytype = models.CharField(max_length=150, choices=ACTIVITY_CHOICES)

    class Meta:
        verbose_name = "Host Activity Type"
        verbose_name_plural = "Host Activity Types"

    def __str__(self):
        name = str(self.activitytype)
        return name

############################################
#       _        _   _       _ _           #
#      / \   ___| |_(_)_   _(_) |_ _   _   #
#     / _ \ / __| __| \ \ / / | __| | | |  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |  #
#                                  |___/   #
############################################

class Activity(models.Model):
    activitytype = models.ForeignKey('provision.ActivityType', related_name='activity_activitytype', null=True)
    mean = models.FloatField(default=0)
    std = models.FloatField(default=0)
    # sdm = models.FloatField(default=0)
    rawrates = models.TextField(default='')
    numsamples = models.IntegerField(default=0)
    host = models.ForeignKey('provision.Host', related_name='activity_host', null=True)
    basefilepath = models.CharField(default='', max_length=256)
    validtime = models.DateTimeField(default=None)
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Host Activity"
        verbose_name_plural = "Host Activities"

    def __str__(self):
        name = str(self.activitytype)
        return name

    def get_mean(self):
        return self.mean

    def get_std(self):
        return self.std

    def get_sdm(self):
        sdm = 0
        if self.mean != 0:
            sdm = self.std / self.mean
        return sdm

    def get_validtime(self):
        dt = self.validtime
        dt = dt.replace(tzinfo=pytz.UTC)
        return dt

    def get_host(self):
        return self.host

    def get_basefilepath(self):
        return self.basefilepath

    def get_rawrates(self):
        rl = []
        rr = str(self.rawrates)
        rr = rr.split(', ')
        for r in rr:
            rl.append(float(r))
        return rl

    def sample_mean(self):
        mean = self.get_mean()
        mean = "{0:.4f}".format(mean)
        return format_html('<span>{}</span>', mean)

    sample_mean.admin_order_field = "mean"

    def sample_std(self):
        std = self.get_std()
        std = "{0:.4f}".format(std)
        return format_html('<span>{}</span>', std)

    sample_std.admin_order_field = "std"

    def std_div_mean(self):
        sdm = self.get_sdm()
        sdm = "{0:.2f}".format(sdm)
        return format_html('<span>{}</span>', sdm)

    std_div_mean.admin_order_field = "sdm"


###################################################################
#       _        _   _       _ _         _____    _       _       #
#      / \   ___| |_(_)_   _(_) |_ _   _|  ___|__| |_ ___| |__    #
#     / _ \ / __| __| \ \ / / | __| | | | |_ / _ \ __/ __| '_ \   #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |  _|  __/ || (__| | | |  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |_|  \___|\__\___|_| |_|  #
#                                  |___/                          #
###################################################################

class ActivityFetch(models.Model):
    numactivities = models.IntegerField(help_text="Number of activities stored", default=0)
    numhosts = models.IntegerField(help_text="Number of unique hosts in this sample", default=0)
    numsamples = models.IntegerField(help_text="Number of unique samples in this fetch", default=0)
    beginfetch = models.IntegerField(help_text="Fetch start time in UTC seconds", default=0)
    fetch_duration = models.IntegerField(help_text="Elapsed seconds fetching samples from cluster", default=0)
    storage_duration = models.IntegerField(help_text="Elapsed seconds storing samples into database", default=0)
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Host Activity Fetch"
        verbose_name_plural = "Host Activity Fetches"

    def __str__(self):
        return str(self.id)

    def get_beginfetch(self):
        return self.beginfetch

    def fetch_date(self):
        bf = float(self.get_beginfetch())
        dt = datetime.datetime.utcfromtimestamp(bf)
        fetchdate = dt.strftime('%Y/%m/%d %H:%M')
        return str(fetchdate)


###############################################################
#       _        _   _       _ _         ____  _        _     #
#      / \   ___| |_(_)_   _(_) |_ _   _/ ___|| |_ __ _| |_   #
#     / _ \ / __| __| \ \ / / | __| | | \___ \| __/ _` | __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |___) | || (_| | |_   #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |____/ \__\__,_|\__|  #
#                                  |___/                      #
###############################################################


class ActivityStat(models.Model):
    activitytype = models.ForeignKey('provision.ActivityType', related_name='activitystat_activitytype', null=True)
    host = models.ForeignKey('provision.Host', related_name='activitystat_host', null=True)
    mean = models.FloatField(default=0.0)
    std = models.FloatField(default=0.0)
    numsamples = models.IntegerField(verbose_name="Number of points", default=0)
    validfrom = models.DateTimeField(verbose_name="Valid From", default='9999-12-31 23:59:59Z')
    validto = models.DateTimeField(verbose_name="Valid To", default='0001-01-01 00:00:01Z')
    validtime = models.DateTimeField(verbose_name="Valid Time", default='5000-06-15 12:30:30Z')
    basefilepath = models.CharField(default='', max_length=256)
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Host Activity Statistic"
        verbose_name_plural = "Host Activity Statistics"

        def __str__(self):
            activity = ACTIVITY_CHOICES[self.get_activitytype()]
            return "{} ({})".format(activity, self.host.name)

    def get_activitytype(self):
        return str(self.activitytype)

    def get_host(self):
        return str(self.host)

    def activity_name(self):
        label = ''
        mytype = self.get_activitytype()
        for (k, v) in ACTIVITY_CHOICES:
            if str(v) in mytype:
                label = str(v)
                break
        name = self.get_host() + " " + label
        return name

    activity_name.admin_order_field = "host"

    def get_validtime(self):
        dt = self.validfrom + (self.validto - self.validfrom) / 2
        # dt = dt.replace(tzinfo=pytz.UTC)
        return dt

    def get_mean(self):
        return self.mean

    def get_numdays(self):
        numdays = self.validto - self.validfrom
        return numdays.days

    def get_std(self):
        return self.std

    def get_sdm(self):
        sdm = 0
        if self.mean != 0:
            sdm = self.std / self.mean
        return sdm

    def population_mean(self):
        mean = self.get_mean()
        mean = "{0:.4f}".format(mean)
        return format_html('<span>{}</span>', mean)

    population_mean.admin_order_field = "mean"

    def population_std(self):
        std = self.get_std()
        std = "{0:.4f}".format(std)
        return format_html('<span>{}</span>', std)

    population_std.admin_order_field = "std"

    def sample_mean(self):
        mean = self.get_mean()
        mean = "{0:.4f}".format(mean)
        return format_html('<span>{}</span>', mean)

    sample_mean.admin_order_field = "mean"

    def sample_std(self):
        std = self.get_std()
        std = "{0:.4f}".format(std)
        return format_html('<span>{}</span>', std)

    sample_std.admin_order_field = "std"

    def std_div_mean(self):
        sdm = self.get_sdm()
        sdm = "{0:.2f}".format(sdm)
        return format_html('<span>{}</span>', sdm)

    std_div_mean.admin_order_field = "sdm"

    def update_all_whole_populations_stats(self):
        noneipz = IPzone.objects.filter(name=settings.NONE_NAME)
        if noneipz.count() < 1:
            msg = "cannot find IPzone " + str(settings.NONE_NAME)
            logger.critical(msg)
            sys.exit(-1)
        else:
            noneipz = noneipz[0]

        noneorg = Organization.objects.filter(name=settings.NONE_NAME)
        if noneorg.count() < 1:
            msg = "cannot find Organization " + str(settings.NONE_NAME)
            logger.critical(msg)
            sys.exit(-1)
        else:
            noneorg = noneorg[0]

        # for each activity type
        for key, choice in ACTIVITY_CHOICES:
            # retain rawrates for whole population
            rawrates = []
            rrvalidfrom = datetime.datetime.strptime('9999-12-31 23:59:59Z', '%Y-%m-%d %H:%M:%SZ')
            rrvalidfrom = rrvalidfrom.replace(tzinfo=pytz.UTC)
            rrvalidto = datetime.datetime.strptime('0001-01-01 00:00:01Z', '%Y-%m-%d %H:%M:%SZ')
            rrvalidto = rrvalidto.replace(tzinfo=pytz.UTC)
            allfilepaths = set()

            # time ranges for this choice
            validfrom = datetime.datetime.strptime('9999-12-31 23:59:59Z', '%Y-%m-%d %H:%M:%SZ')
            validfrom = validfrom.replace(tzinfo=pytz.UTC)
            validto = datetime.datetime.strptime('0001-01-01 00:00:01Z', '%Y-%m-%d %H:%M:%SZ')
            validto = validto.replace(tzinfo=pytz.UTC)

            qs = ActivityType.objects.filter(activitytype=choice)
            if qs.count() != 1:
                msg = "count not find activity type " + str(choice)
                logger.critical(msg)
                sys.exit(-1)
            else:
                activitytype = qs[0]

            # gather data by hostid
            byhostid = {}
            allacts = Activity.objects.filter(activitytype=activitytype)
            msg = "found " + str(len(allacts)) + " activity objects for activity type " + str(activitytype)
            logger.info(msg)
            for act in allacts:
                host = act.get_host()
                if settings.NONE_NAME in str(host):
                    continue
                hostid = host.id
                try:
                    test = byhostid[hostid]
                except:
                    byhostid[hostid] = {}
                    byhostid[hostid]['rawrates'] = []
                    byhostid[hostid]['validfrom'] = validfrom
                    byhostid[hostid]['validto'] = validto
                    byhostid[hostid]['filepaths'] = set()
                rr = act.get_rawrates()
                for r in rr:
                    byhostid[hostid]['rawrates'].append(float(r))
                actvalidtime = act.get_validtime()
                if actvalidtime < byhostid[hostid]['validfrom']:
                    byhostid[hostid]['validfrom'] = actvalidtime
                    rrvalidfrom = actvalidtime
                if actvalidtime > byhostid[hostid]['validto']:
                    byhostid[hostid]['validto'] = actvalidtime
                    rrvalidto = actvalidtime
                byhostid[hostid]['filepaths'].add(act.get_basefilepath())
                allfilepaths.add(act.get_basefilepath())

            # organize byhostid data by organization
            byorg = {}
            msg = "found " + str(len(byhostid.keys())) + " byhostid keys"
            logger.info(msg)
            for hostid in byhostid.keys():
                hqs = Host.objects.filter(id=hostid)
                if hqs.count() == 1:
                    host = hqs[0]
                    if settings.NONE_NAME in str(host) or 'None' in str(host):
                        msg = "   found NONE in host " + str(host.getip())
                        logger.info(msg)
                        # continue
                    org = str(host.get_organization())
                    if settings.NONE_NAME in str(org) or 'None' in str(org):
                        msg = "   found NONE in org " + str(org) + " for host " + str(host.getip())
                        # org = str(host.getip())
                        org = str(host)
                        logger.info(msg)
                    try:
                        test = byorg[org]
                    except:
                        byorg[org] = {}
                        byorg[org]['hostids'] = set()
                    byorg[org]['hostids'].add(hostid)
                    byorg[org]['mean'] = avg_calc(byhostid[hostid]['rawrates'])
                    byorg[org]['std'] = sd_calc(byhostid[hostid]['rawrates'])
                    byorg[org]['numpts'] = len(byhostid[hostid]['rawrates'])
                    byorg[org]['validfrom'] = byhostid[hostid]['validfrom']
                    byorg[org]['validto'] = byhostid[hostid]['validto']
                    byorg[org]['filepaths'] = byhostid[hostid]['filepaths']
                    for r in byhostid[hostid]['rawrates']:
                        rawrates.append(r)
                else:
                    msg = " could not find host with id " + str(hostid)
                    logger.critical(msg)
                    sys.exit(-1)

                # Activity stats for this host
                hostmean = avg_calc(byhostid[hostid]['rawrates'])
                hoststd = sd_calc(byhostid[hostid]['rawrates'])
                hostnumpts = len(byhostid[hostid]['rawrates'])
                basefilepath = byhostid[hostid]['filepaths']
                if len(allfilepaths) > 1:
                    basefilepath = []
                    for fp in allfilepaths:
                        basefilepath.append(fp)
                    basefilepath.sort()
                    basefilepath = basefilepath[0]
                qs = ActivityStat.objects.filter(activitytype=activitytype, host=host)
                if qs.count() == 0:
                    validtime = byhostid[hostid]['validfrom'] + (
                                byhostid[hostid]['validto'] - byhostid[hostid]['validfrom']) / 2
                    hostactstat = ActivityStat(activitytype=activitytype, host=host, mean=hostmean, std=hoststd,
                                               numsamples=hostnumpts,
                                               validfrom=byhostid[hostid]['validfrom'],
                                               validto=byhostid[hostid]['validto'], validtime=validtime,
                                               basefilepath=basefilepath)
                else:
                    hostactstat = qs[0]
                    hostactstat.mean = hostmean
                    hostactstat.std = hoststd
                    hostactstat.samples = hostnumpts
                    hostactstat.validfrom = byhostid[hostid]['validfrom']
                    hostactstat.validto = byhostid[hostid]['validto']
                    hostactstat.validtime = byhostid[hostid]['validfrom'] + (
                                byhostid[hostid]['validto'] - byhostid[hostid]['validfrom']) / 2
                    hostactstat.basefilepath = basefilepath
                hostactstat.save()

            # store all organizations stats
            hostname = "all_Organizations_stats"
            qs = Host.objects.filter(name=hostname)
            if qs.count() < 1:
                host = Host(name=hostname, ipaddr='0.0.0.0', ipzone=noneipz, organization=noneorg)
                host.save()
                now = datetime.datetime.utcnow()
                msg = str(now) + ":addHost:" + str(host) + ":update_all_whole_populations_stats"
                logger.info(msg)
            else:
                host = qs[0]
            msg = "     host is " + str(host)
            logger.info(msg)
            if len(rawrates) < 2:
                msg = "  not enough raw rate data for activity type " + str(choice)
                logger.info(msg)
                continue

            # Activity stats for the whole population of organizations
            wholepopmean = avg_calc(rawrates)
            wholepopstd = sd_calc(rawrates)
            wholepopnumpts = len(rawrates)
            basefilepath = 'unknown'
            if len(allfilepaths) > 1:
                basefilepath = []
                for fp in allfilepaths:
                    basefilepath.append(fp)
                basefilepath.sort()
                basefilepath = basefilepath[0]
            qs = ActivityStat.objects.filter(activitytype=activitytype, host=host)
            if qs.count() == 0:
                validtime = rrvalidto - rrvalidfrom
                wpactstat = ActivityStat(activitytype=activitytype, host=host, mean=wholepopmean, std=wholepopstd,
                                         numsamples=wholepopnumpts,
                                         validfrom=rrvalidfrom, validto=rrvalidto, validtime=validtime,
                                         basefilepath=basefilepath)
            else:
                wpactstat = qs[0]
                wpactstat.mean = wholepopmean
                wpactstat.std = wholepopstd
                wpactstat.numsamples = wholepopnumpts
                wpactstat.validfrom = rrvalidfrom
                wpactstat.validto = rrvalidto
                wpactstat.basefilepath = basefilepath

            now = datetime.datetime.utcnow()
            msg = str(now)
            if wpactstat.get_std() != 0.0 and wpactstat.get_mean() != 0.0:
                wpactstat.save()
                msg = msg + ":saveActivityStatwp:" + str(
                    wpactstat.activity_name()) + ":update_all_whole_populations_stats"
            else:
                msg = msg + ":skippingsaveActivityStatwp:" + str(
                    wpactstat.activity_name()) + ":update_all_whole_populations_stats"
            logger.info(msg)

            # create activity stats by organization
            for org in byorg.keys():
                hostname = str(org) + "_host_activity_stats"
                hostname = hostname.lower()
                qs = Host.objects.filter(name=hostname)
                if qs.count() < 1:
                    host = Host(name=hostname, ipaddr='0.0.0.0', ipzone=noneipz, organization=noneorg)
                    host.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addHost:" + str(host) + ":update_all_whole_populations_stats"
                    logger.info(msg)
                else:
                    host = qs[0]
                mean = byorg[org]['mean']
                std = byorg[org]['std']
                numpts = byorg[org]['numpts']
                validfrom = byorg[org]['validfrom']
                validto = byorg[org]['validto']
                db = validto - validfrom
                qr = DaysInDataset.objects.filter(days=db.days)
                if qr.count() != 1:
                    daysback = DaysInDataset(days=db.days, label=str(db.days))
                    daysback.save()
                else:
                    daysback = qr[0]

                if len(byorg[org]['filepaths']) > 1:
                    basefilepath = []
                    for fp in byorg[org]['filepaths']:
                        basefilepath.append(fp)
                    basefilepath.sort()
                    basefilepath = basefilepath[0]

                qs = ActivityStat.objects.filter(activitytype=activitytype, host=host)
                if qs.count() == 0:
                    validtime = validfrom + (validto - validfrom) / 2
                    actstat = ActivityStat(activitytype=activitytype, host=host, mean=mean, std=std, numsamples=numpts,
                                           validfrom=validfrom, validto=validto, validtime=validtime,
                                           basefilepath=basefilepath)
                else:
                    actstat = qs[0]
                    actstat.mean = mean
                    actstat.std = std
                    actstat.numsamples = numpts
                    actstat.validfrom = validfrom
                    actstat.validto = validto
                    actstat.validtime = validfrom + (validto - validfrom) / 2
                    actstat.basefilepath = basefilepath
                actstat.save()
                now = datetime.datetime.utcnow()
                msg = str(now) + ":saveActivityStat:" + str(
                    actstat.activity_name()) + ":update_all_whole_populations_stats"
                logger.info(msg)

                # stats for this organization versus whole population of organizations
                hostname = str(org).lower() + " vs All_Organizations_stats"
                qs = Host.objects.filter(name=hostname)
                if qs.count() < 1:
                    host = Host(name=hostname, ipaddr='0.0.0.0', ipzone=noneipz, organization=noneorg)
                    host.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addHost:" + str(host) + ":update_all_whole_populations_stats"
                    logger.info(msg)
                else:
                    host = qs[0]

                # compare this org versus the whole population
                meandiff = float(byorg[org]['mean']) - wholepopmean
                stdorg = float(byorg[org]['std'])
                stddiff = stdorg - wholepopstd
                v1 = math.sqrt(stdorg)
                vwp = math.sqrt(wholepopstd)
                variancediff = v1 - vwp
                if wholepopstd != 0.0:
                    ratio_of_std = stdorg / wholepopstd
                else:
                    ratio_of_std = 0
                if vwp != 0.0:
                    ratio_of_variance = v1 / vwp
                else:
                    ratio_of_variance = 0
                qs = ActivityStatComp.objects.filter(activitytype=activitytype, host=host, days_in_dataset=daysback)
                if qs.count() == 0:
                    actstatcomp = ActivityStatComp(activitytype=activitytype, host=host, meandiff=meandiff,
                                                   stddiff=stddiff,
                                                   variancediff=variancediff, ratio_of_std=ratio_of_std,
                                                   ratio_of_variance=ratio_of_variance, days_in_dataset=daysback,
                                                   validfrom=validfrom, validto=validto)
                else:
                    actstatcomp = qs[0]
                    actstatcomp.meandiff = meandiff
                    actstatcomp.stddiff = stddiff
                    actstatcomp.variancediff = variancediff
                    actstatcomp.stdratio = ratio_of_std
                    actstat.varianceratio = ratio_of_variance
                    actstatcomp.validfrom = validfrom
                    actstatcomp.validto = validto
                    actstatcomp.basefilepath = basefilepath
                    actstatcomp.days_in_dataset = daysback
                actstatcomp.save()
                now = datetime.datetime.utcnow()
                msg = str(now) + ":saveActivityStatComp:" + str(
                    actstatcomp.activity_name()) + ":update_all_whole_populations_stats"
                logger.info(msg)

    def update_all_running_activity_stats(self):
        noneipz = IPzone.objects.filter(name=settings.NONE_NAME)
        if noneipz.count() < 1:
            msg = "cannot find IPzone " + str(settings.NONE_NAME)
            logger.critical(msg)
            sys.exit(-1)
        else:
            noneipz = noneipz[0]

        noneorg = Organization.objects.filter(name=settings.NONE_NAME)
        if noneorg.count() < 1:
            msg = "cannot find Organization " + str(settings.NONE_NAME)
            logger.critical(msg)
            sys.exit(-1)
        else:
            noneorg = noneorg[0]

        # for each activity type
        ackeys = []
        for key, choice in ACTIVITY_CHOICES:
            ackeys.append(int(key))

        # for all activity types
        for i in range(0, len(ackeys)):
            key = int(ACTIVITY_CHOICES[i][0])
            choice = str(ACTIVITY_CHOICES[i][1])
            choice = choice.strip().encode('ascii', 'ignore')

            qs = ActivityType.objects.filter(activitytype=choice)
            if qs.count() != 1:
                msg = "count not find activity type " + str(choice)
                logger.critical(msg)
                sys.exit(-1)
            else:
                activitytype = qs[0]

            msg = "   activitytype = " + str(activitytype) + " for " + str(key) + ", " + str(choice)
            # logger.info(msg)

            for dds in DaysInDataset.objects.all().order_by('days'):
                daysback = dds.get_days()
                label = dds.get_label()

                # data set desired times
                dsdesiredvalidto = datetime.datetime.utcnow()
                dsdesiredvalidto = dsdesiredvalidto.replace(tzinfo=pytz.UTC)
                dsdesiredvalidto = dsdesiredvalidto.replace(hour=0, minute=0, second=0, microsecond=0)
                dbp1 = daysback + 1
                dsdesiredvalidfrom = dsdesiredvalidto - datetime.timedelta(days=dbp1)

                # times found in the dataset
                dsfoundvalidfrom = datetime.datetime.strptime('9999-12-31 23:59:59Z', '%Y-%m-%d %H:%M:%SZ')
                dsfoundvalidfrom = dsfoundvalidfrom.replace(tzinfo=pytz.UTC)
                dsfoundvalidto = datetime.datetime.strptime('0001-01-01 00:00:01Z', '%Y-%m-%d %H:%M:%SZ')
                dsfoundvalidto = dsfoundvalidto.replace(tzinfo=pytz.UTC)

                # retain rawrates for whole population
                rawrates = []
                rrvalidfrom = datetime.datetime.strptime('9999-12-31 23:59:59Z', '%Y-%m-%d %H:%M:%SZ')
                rrvalidfrom = rrvalidfrom.replace(tzinfo=pytz.UTC)
                rrvalidto = datetime.datetime.strptime('0001-01-01 00:00:01Z', '%Y-%m-%d %H:%M:%SZ')
                rrvalidto = rrvalidto.replace(tzinfo=pytz.UTC)
                allfilepaths = set()

                # gather data by hostid
                byhostid = {}
                dsrange = []
                dsrange.append(str(dsdesiredvalidfrom))
                dsrange.append(str(dsdesiredvalidto))
                allacts = Activity.objects.filter(activitytype=activitytype, validtime__range=dsrange)
                lenacts = len(allacts)
                msg = "   found " + str(lenacts) + " " + str(activitytype) + " Activity objects"
                logger.info(msg)
                for act in allacts:
                    host = act.get_host()
                    hostid = host.id
                    try:
                        test = byhostid[hostid]
                    except:
                        byhostid[hostid] = {}
                        byhostid[hostid]['rawrates'] = []
                        byhostid[hostid]['validfrom'] = dsfoundvalidfrom
                        byhostid[hostid]['validto'] = dsfoundvalidto
                        byhostid[hostid]['filepaths'] = set()
                    rr = act.get_rawrates()
                    for r in rr:
                        byhostid[hostid]['rawrates'].append(float(r))
                    actvalidtime = act.get_validtime()
                    if actvalidtime <= byhostid[hostid]['validfrom']:
                        byhostid[hostid]['validfrom'] = actvalidtime
                        rrvalidfrom = actvalidtime
                        dsfoundvalidfrom = actvalidtime
                    if actvalidtime >= byhostid[hostid]['validto']:
                        byhostid[hostid]['validto'] = actvalidtime
                        rrvalidto = actvalidtime
                        dsfoundvalidto = actvalidtime
                    byhostid[hostid]['filepaths'].add(act.get_basefilepath())
                    allfilepaths.add(act.get_basefilepath())
                    for r in byhostid[hostid]['rawrates']:
                        rawrates.append(r)

                # organize byhostid data by organization
                byorg = {}
                for hostid in byhostid.keys():
                    hqs = Host.objects.filter(id=hostid)
                    if hqs.count() == 1:
                        host = hqs[0]
                        if settings.NONE_NAME in str(host):
                            continue
                        org = str(host.get_organization())
                        if settings.NONE_NAME in str(org):
                            continue
                        try:
                            test = byorg[org]
                        except:
                            byorg[org] = {}
                            byorg[org]['hostids'] = set()
                        byorg[org]['hostids'].add(hostid)
                        byorg[org]['mean'] = avg_calc(byhostid[hostid]['rawrates'])
                        byorg[org]['std'] = sd_calc(byhostid[hostid]['rawrates'])
                        byorg[org]['numpts'] = len(byhostid[hostid]['rawrates'])
                        byorg[org]['validfrom'] = byhostid[hostid]['validfrom']
                        byorg[org]['validto'] = byhostid[hostid]['validto']
                        byorg[org]['filepaths'] = byhostid[hostid]['filepaths']
                        for r in byhostid[hostid]['rawrates']:
                            rawrates.append(r)
                    else:
                        msg = " could not find host with id " + str(hostid)
                        logger.critical(msg)
                        sys.exit(-1)

                # store all organizations stats
                hostname = label + " All_Organizations_stats"
                qs = Host.objects.filter(name=hostname)
                if qs.count() < 1:
                    host = Host(name=hostname, ipaddr='0.0.0.0', ipzone=noneipz, organization=noneorg)
                    host.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":addHost:" + str(host) + ":update_all_whole_populations_stats"
                    logger.info(msg)
                else:
                    host = qs[0]

                if len(rawrates) < 2:
                    msg = "  not enough raw rate data for daysback " + str(daysback) + " and " + str(
                        label) + " and " + str(choice)
                    logger.critical(msg)
                    continue

                td = dsfoundvalidto - dsfoundvalidfrom
                totaldays = td.days
                if totaldays != daysback:
                    msg = "  incorrect data length -- daysback is " + str(daysback) + " and total is " + str(
                        totaldays) + " for " + str(label) + " and " + str(choice)
                    logger.info(msg)
                    continue

                # Activity stats for the whole population of organizations
                wholepopmean = avg_calc(rawrates)
                wholepopstd = sd_calc(rawrates)
                wholepopnumpts = len(rawrates)
                basefilepath = []
                if len(allfilepaths) > 1:
                    for fp in allfilepaths:
                        basefilepath.append(fp)
                    basefilepath.sort()
                    basefilepath = basefilepath[0]
                qs = ActivityRunningStat.objects.filter(activitytype=activitytype, host=host, days_in_dataset=dds)
                msg = "  found " + str(qs.count()) + " ActivityRunningStat " + str(activitytype) + " objects"
                logger.info(msg)

                if qs.count() == 0:
                    actstat = ActivityRunningStat(activitytype=activitytype, host=host, mean=wholepopmean,
                                                  std=wholepopstd,
                                                  numsamples=wholepopnumpts, validfrom=rrvalidfrom, validto=rrvalidto,
                                                  basefilepath=basefilepath, days_in_dataset=dds)
                else:
                    actstat = qs[0]
                    msg = "   actstat is " + str(actstat)
                    logger.info(msg)
                    msg = "      host is " + str(actstat.host)
                    logger.info(msg)
                    msg = "      wpnpts = " + str(wholepopnumpts)
                    logger.info(msg)
                    actstat.mean = wholepopmean
                    actstat.std = wholepopstd
                    actstat.numsamples = wholepopnumpts
                    actstat.validfrom = rrvalidfrom
                    actstat.validto = rrvalidto
                    actstat.basefilepath = basefilepath
                    actstat.days_in_dataset = dds
                actstat.save()
                now = datetime.datetime.utcnow()
                msg = str(now) + ":saveActivityRunningStat:" + str(
                    actstat.activity_name()) + ":update_all_whole_populations_stats"
                logger.info(msg)

                # create activity running stats by organization
                for org in byorg.keys():
                    hostname = label + "_" + str(org).lower() + "_host_activity_stats"
                    hostname = hostname.lower()
                    qs = Host.objects.filter(name=hostname)
                    if qs.count() < 1:
                        host = Host(name=hostname, ipaddr='0.0.0.0', ipzone=noneipz, organization=noneorg)
                        host.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addHost:" + str(host) + ":update_all_whole_populations_stats"
                        logger.info(msg)
                    else:
                        host = qs[0]
                    mean = byorg[org]['mean']
                    std = byorg[org]['std']
                    numpts = byorg[org]['numpts']
                    validfrom = byorg[org]['validfrom']
                    validto = byorg[org]['validto']
                    if len(byorg[org]['filepaths']) > 1:
                        basefilepath = []
                        for fp in byorg[org]['filepaths']:
                            basefilepath.append(fp)
                        basefilepath.sort()
                        basefilepath = basefilepath[0]

                    qs = ActivityRunningStat.objects.filter(activitytype=activitytype, host=host, days_in_dataset=dds)
                    if qs.count() == 0:
                        actstat = ActivityRunningStat(activitytype=activitytype, host=host, mean=mean, std=std,
                                                      numsamples=numpts,
                                                      validfrom=validfrom, validto=validto, basefilepath=basefilepath,
                                                      days_in_dataset=dds)
                    else:
                        actstat = qs[0]
                        actstat.mean = mean
                        actstat.std = std
                        actstat.numsamples = numpts
                        actstat.validfrom = validfrom
                        actstat.validto = validto
                        actstat.days_in_dataset = dds
                        actstat.basefilepath = basefilepath
                    actstat.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":saveActivityRunningStat:" + str(
                        actstat.activity_name()) + ":update_all_whole_populations_stats"
                    logger.info(msg)

                    # activity stat comparison
                    hostname = label + "_" + str(org).lower() + "_vs_All_Organizations_stats"
                    qs = Host.objects.filter(name=hostname)
                    if qs.count() < 1:
                        host = Host(name=hostname, ipaddr='0.0.0.0', ipzone=noneipz, organization=noneorg)
                        host.save()
                        now = datetime.datetime.utcnow()
                        msg = str(now) + ":addHost:" + str(host) + ":update_all_whole_populations_stats"
                        logger.info(msg)
                    else:
                        host = qs[0]

                    # compare this org versus the whole population
                    meandiff = float(byorg[org]['mean']) - wholepopmean
                    stdorg = float(byorg[org]['std'])
                    stddiff = stdorg - wholepopstd
                    v1 = math.sqrt(stdorg)
                    vwp = math.sqrt(wholepopstd)
                    variancediff = v1 - vwp
                    if wholepopstd != 0.0:
                        stdratio = stdorg / wholepopstd
                    else:
                        stdratio = 0
                    if vwp != 0.0:
                        varianceratio = v1 / vwp
                    else:
                        varianceratio = 0
                    qs = ActivityStatComp.objects.filter(activitytype=activitytype, host=host, days_in_dataset=dds)
                    if qs.count() == 0:
                        actstat = ActivityStatComp(activitytype=activitytype, host=host, meandiff=meandiff,
                                                   stddiff=stddiff, variancediff=variancediff, ratio_of_std=stdratio,
                                                   ratio_of_variance=varianceratio,
                                                   validfrom=validfrom, validto=validto, days_in_dataset=dds)
                    else:
                        actstat = qs[0]
                        actstat.meandiff = meandiff
                        actstat.stddiff = stddiff
                        actstat.variancediff = variancediff
                        actstat.stdratio = stdratio
                        actstat.varianceratio = varianceratio
                        actstat.validfrom = validfrom
                        actstat.validto = validto
                        actstat.days_in_dataset = dds
                        actstat.basefilepath = basefilepath
                    actstat.save()
                    now = datetime.datetime.utcnow()
                    msg = str(now) + ":saveActivityStatComp:" + str(
                        actstat.activity_name()) + ":update_all_whole_populations_stats"
                    logger.info(msg)


######################################################################################################
#       _        _   _       _ _         ____                    _              ____  _        _     #
#      / \   ___| |_(_)_   _(_) |_ _   _|  _ \ _   _ _ __  _ __ (_)_ __   __ _ / ___|| |_ __ _| |_   #
#     / _ \ / __| __| \ \ / / | __| | | | |_) | | | | '_ \| '_ \| | '_ \ / _` |\___ \| __/ _` | __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |  _ <| |_| | | | | | | | | | | | (_| | ___) | || (_| | |_   #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |_| \_\\__,_|_| |_|_| |_|_|_| |_|\__, ||____/ \__\__,_|\__|  #
#                                  |___/                                 |___/                       #
######################################################################################################


class ActivityRunningStat(ActivityStat):
    name = models.CharField(default='running statistic', max_length=128)
    days_in_dataset = models.ForeignKey('provision.DaysInDataset',
                                        verbose_name="Number of days included in this dataset",
                                        help_text="Number of days included in this dataset, starting from the validto date")

    class Meta:
        verbose_name = "Host Activity Running Statistic"
        verbose_name_plural = "Host Activity Running Statistics"

        def __str__(self):
            return str(self.host)

    def get_numdays(self):
        return self.days_in_dataset


class ActivityStatComp(models.Model):
    activitytype = models.ForeignKey('provision.ActivityType', related_name='activitystatcomp_activitytype', null=True)
    host = models.ForeignKey('provision.Host', related_name='activitystatcomp_host', null=True)
    days_in_dataset = models.ForeignKey('provision.DaysInDataset',
                                        verbose_name="Number of days included in this dataset",
                                        help_text="Number of days included in this dataset, starting from the validto date",
                                        null=True)
    meandiff = models.FloatField(default=0.0)
    stddiff = models.FloatField(default=0.0)
    variancediff = models.FloatField(default=0.0)
    ratio_of_std = models.FloatField(default=0.0)
    ratio_of_variance = models.FloatField(default=0.0)
    validfrom = models.DateTimeField(verbose_name="Valid From", default='9999-12-31 23:59:59Z')
    validto = models.DateTimeField(verbose_name="Valid To", default='0001-01-01 00:00:01Z')
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Host Activity Statistic Comparison"
        verbose_name_plural = "Host Activity Statistic Comparisons"

        def __str__(self):
            name = ACTIVITY_CHOICES[self.get_activitytype()]
            return name

    def get_activitytype(self):
        return str(self.activitytype)

    def get_numdays(self):
        return self.days_in_dataset

    def get_host(self):
        return str(self.host)

    def activity_name(self):
        label = ''
        mytype = self.get_activitytype()
        for (k, v) in ACTIVITY_CHOICES:
            if str(v) in mytype:
                label = str(v)
                break
        name = self.get_host() + " " + label
        return name

    activity_name.admin_order_field = "host"

    def get_meandiff(self):
        return self.meandiff

    def get_stddiff(self):
        return self.stddiff

    def get_variancediff(self):
        return self.variancediff

    def get_stdratio(self):
        return self.ratio_of_std

    def get_varianceratio(self):
        return self.ratio_of_variance

    def meandifference(self):
        meandiff = self.get_meandiff()
        meandiff = "{0:.4f}".format(meandiff)
        return format_html('<span>{}</span>', meandiff)

    meandifference.admin_order_field = "meandiff"

    def stddifference(self):
        stddiff = self.get_stddiff()
        stddiff = "{0:.4f}".format(stddiff)
        return format_html('<span>{}</span>', stddiff)

    stddifference.admin_order_field = "stddiff"

    def variancedifference(self):
        vardiff = self.get_variancediff()
        vardiff = "{0:.4f}".format(vardiff)
        return format_html('<span>{}</span>', vardiff)

    variancedifference.admin_order_field = "variancediff"

    def stdratio(self):
        stdratio = self.get_stdratio()
        stdratio = "{0:.4f}".format(stdratio)
        return format_html('<span>{}</span>', stdratio)

    stdratio.admin_order_field = "ratio_of_std"

    def varianceratio(self):
        varratio = self.get_varianceratio()
        varratio = "{0:.4f}".format(varratio)
        return format_html('<span>{}</span>', varratio)

    varianceratio.admin_order_field = "varianceratio"


#########################################################
#     ____ _           _            ____  _       _     #
#    / ___| |_   _ ___| |_ ___ _ __/ ___|| | ___ | |_   #
#   | |   | | | | / __| __/ _ \ '__\___ \| |/ _ \| __|  #
#   | |___| | |_| \__ \ ||  __/ |   ___) | | (_) | |_   #
#    \____|_|\__,_|___/\__\___|_|  |____/|_|\___/ \__|  #
#                                                       #
#########################################################


class ClusterSlot(models.Model):
    slot = models.IntegerField(default=0, help_text="test")
    capacity = models.BigIntegerField(default=0)
    disk_model = models.CharField(max_length=64)
    slot_type = models.CharField(max_length=8)
    state = models.CharField(max_length=12)
    node_id = models.IntegerField(default=0)
    disk_type = models.CharField(max_length=8)
    qid = models.CharField(max_length=8)

    class Meta:
        verbose_name = "Cluster Slot"
        verbose_name_plural = "Cluster Slots"

    def __str__(self):
        return str(self.qid)

    def get_node_id(self):
        return int(self.node_id)


class ClusterTimeSeriesType(models.Model):
    activitytype = models.CharField(max_length=150, choices=CLUSTER_TIME_SERIES_CHOICES)

    class Meta:
        verbose_name = "Cluster Time Series Type"
        verbose_name_plural = "Cluster Time Activity Types"

    def __str__(self):
        name = str(self.activitytype)
        return name


class ClusterTimeSeries(models.Model):
    activitytype = models.ForeignKey('provision.ClusterTimeSeriesType', related_name='clustertimeseries_activitytype',
                                     null=True)
    mean = models.FloatField(default=0)
    std = models.FloatField(default=0)
    # sdm = models.FloatField(default=0)
    rawrates = models.TextField(default='')
    numsamples = models.IntegerField(default=0)
    # host = models.ForeignKey('provision.Host', related_name='clustertimeseries_host', null=True)
    basefilepath = models.CharField(default='', max_length=256)
    updated = models.DateTimeField(auto_now_add=True)


class ClusterNode(models.Model):
    name = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Cluster Node"
        verbose_name_plural = "Cluster Nodes"

    def __str__(self):
        return str(self.name)


class ConnectionFetch(models.Model):
    numhosts = models.IntegerField(help_text="Number of unique hosts in this sample", default=0)
    numconnections = models.IntegerField(help_text="Number of connections in this fetch", default=0)
    beginfetch = models.IntegerField(help_text="Fetch start time in UTC seconds", default=0)
    fetch_duration = models.FloatField(help_text="Elapsed seconds fetching samples from cluster", default=0)
    storage_duration = models.FloatField(help_text="Elapsed seconds storing samples into database", default=0)
    connections = models.ManyToManyField('provision.connection', related_name='provision_connection')
    updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Host Connection Fetch"
        verbose_name_plural = "Host Connection Fetches"

    def __str__(self):
        return str(self.id)

    def get_connection_id(self):
        return self.connection_id

    def set_connection(self, org):
        self.organization = org
        self.save()

    def avg_CBH(self):
        if float(self.numhosts) != float(0.0):
            avgcbh = float(self.numconnections) / float(self.numhosts)
            avgcbh = "{0:.2f}".format(avgcbh)
        else:
            avgcbh = 0.0
        return format_html('<span>{}</span>', avgcbh)

    def host_connections_link(self):
        # http://127.0.0.1:8000/admin/provision/connectionfetch/21/change/
        links = ''
        for c in self.connections.all():
            id = c.get_id()
            name = str(c)
            numconnections = int(0)
            numhosts = int(0)
            q = str(c.get_cbh())
            q = q.replace("u'", "'", 100)
            ale = ast.literal_eval(q)
            numhosts = len(ale)
            for xd in ale:
                hostnames = xd.keys()
                for host in hostnames:
                    numconnections = numconnections + int(xd[host])
            url = reverse("admin:provision_connection_change", args=[id])
            links = links + '<a href="%s">%s -- %s connections to %s hosts</a>' % (
            url, name, numconnections, numhosts) + "<br>\n"
        return mark_safe(links)

    def node_id_list(self):
        # http://127.0.0.1:8000/admin/provision/connectionfetch/21/change/
        nodeids = []
        for c in self.connections.all():
            nodeids.append(int(c.get_nodeid()))
        msg = ''
        for node in nodeids:
            msg = msg + str(node) + ", "
        msg = re.sub(", $", "", msg)
        return str(msg)


class ConnectionType(models.Model):
    name = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Connection Type"
        verbose_name_plural = "Connection Types"

    def __str__(self):
        return str(self.name)


class Connection(models.Model):
    nodeid = models.ForeignKey('provision.ClusterNode', related_name='connection_clusternode', null=True)
    connectiontype = models.ForeignKey('provision.ConnectionType', related_name='connection_connectiontype', null=True)
    connections_per_host = models.TextField(default="{}", max_length=200)
    hosts_by_num_connections = models.TextField(default="{}", max_length=150)
    validtime = models.DateTimeField(default='0001-01-01 00:00:01Z')

    class Meta:
        verbose_name = "Host Connection"
        verbose_name_plural = "Host Connections"

    def __str__(self):
        name = "Node " + str(self.nodeid) + ": " + str(self.id) + " -- " + str(self.validtime)
        return name

    def get_id(self):
        return self.id

    def get_nodeid(self):
        return str(self.nodeid)

    def get_cbh(self):
        return self.connections_per_host

    def get_hbc(self):
        return self.hosts_by_num_connections

    def num_CBH(self):
        return int(len(self.get_cbh()))

    def Connections_By_Host(self):

        cbh = {}
        q = str(self.get_cbh())
        q = q.replace("u'", "'", 100)
        ale = ast.literal_eval(q)
        for xd in ale:
            for k in xd.keys():
                cbh[k] = xd[k]

        hostnames = cbh.keys()
        hostnames.sort()
        msg = "<ul>\n"
        for h in hostnames:
            msg = msg + "<li>" + str(h) + ": " + str(cbh[h]) + "</li>\n"
        if len(msg) < 2:
            msg = "No connections"
        else:
            msg = msg + "</ul>"

        return format_html(msg)

    Connections_By_Host.short_description = "Number of Connections By Host"

    def Hosts_By_Connection(self):

        hbc = {}
        q = str(self.get_hbc())
        q = q.replace("u'", "'", 100)
        xd = ast.literal_eval(q)
        for k in xd.keys():
            try:
                test = hbc[k]
            except:
                hbc[k] = []
            for h in xd[k]:
                hbc[k].append(h)

        connections = hbc.keys()
        connections.sort(reverse=True)
        msg = "<ul>\n"
        for c in connections:
            stuff = str(hbc[c])
            stuff = stuff.replace("]", "")
            stuff = stuff.replace("[", "")
            stuff = stuff.replace("'", "", 1000000)
            msg = msg + "<li>" + str(c) + ": " + stuff + "</li>\n"
        if len(msg) < 2:
            msg = "No connections"
        else:
            msg = msg + "</ul>"

        return format_html(msg)

    Hosts_By_Connection.short_description = "Hosts by Number of Connections"

#########################################################
#    ____   ___  ____ _____   ____    ___     _______   #
#   |  _ \ / _ \/ ___|_   _| / ___|  / \ \   / / ____|  #
#   | |_) | | | \___ \ | |   \___ \ / _ \ \ / /|  _|    #
#   |  __/| |_| |___) || |    ___) / ___ \ V / | |___   #
#   |_|    \___/|____/ |_|___|____/_/   \_\_/  |_____|  #
#                       |_____|                         #
#########################################################


# https://coderwall.com/p/ktdb3g/django-signals-an-extremely-simplified-explanation-for-beginners
@receiver(post_save, sender='provision.Restriction')
def post_save_restriction(sender, **kwargs):
    # Locate and save (update) associated NSF exports
    # collect parents as a set since theoretically a restriction could be used by more than one export
    # note: this code is necessarily repeated in restriction.save()
    updated_fields = kwargs.get('update_fields')
    myself = kwargs.get('instance')

    nsfparents = set()
    for x in NfsExport.objects.all():
        xrqs = x.get_restrictions()
        for xr in xrqs:
            if myself == xr:
                nsfparents.add(x)

    for x in nsfparents:
        now = datetime.datetime.utcnow()
        msg = str(now) + " in post_save_restriction nfsparent is " + str(x)
        logger.info(msg)
        qs = NfsExport.objects.filter(id=x.id)
        if qs.count() == 1:
            qs[0].save(update_on_cluster=True)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":post_save_restriction nfs parent is " + str(qs[0]) + " for restriction " + str(myself)
            logger.info(msg)


@receiver(post_save, sender='provision.IPZone')
def post_save_ipzone(sender, **kwargs):
    #   Locate and save (update) associated NFS Restrictions and then NFS Exports, but only if immutable flag is False (the default -- so that GUI created objects are deleted)
    #   this code is necessarily repeated in post_save_ipzone()
    myself = kwargs.get('instance')
    rpset = set()
    for r in Restriction.objects.all():
        ipzones = r.get_ipzones()
        for z in ipzones:
            if myself == z:
                rpset.add(r)

    for r in rpset:
        r.save()
        now = datetime.datetime.utcnow()
        msg = str(now) + ":post_save_ipzone restriction parent is " + str(r) + " for ipzone " + str(myself)
        logger.info(msg)

    nsfxparents = set()
    for x in NfsExport.objects.all():
        xrqs = x.restrictions.get_queryset()
        for xr in xrqs:
            for r in rpset:
                if r == xr:
                    nsfxparents.add(x)

    for x in nsfxparents:
        x.save(update_on_cluster=True)
        now = datetime.datetime.utcnow()
        msg = str(now) + ":post_save_ipzone nfs parent is " + str(x) + " for ipzone " + str(myself)
        logger.info(msg)


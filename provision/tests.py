# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

from django.test import TestCase
from .models import OrganizationExcludes, Quota, Cluster, Clusterpath, IPzone, Organization, Host, WinDC, DNSdomain, \
    Report, Sysadmin, Restriction

# Qumulo REST libraries
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import qumulo.lib.auth
import qumulo.lib.request as request
import qumulo.rest

from qrba import settings

class Testparams():
    goodclustername = settings.QUMULO_devcluster['name']
    goodclusteradminpassword = settings.QUMULO_devcluster['adminpassword']
    goodclusterip = settings.QUMULO_devcluster['ipaddr']

    # These must be gleaned from from the domain controller -- but this provides the pattern
    goodipzone = "domain.org.tld/ANORG/UNIX/Zones/A_GROUP_NAME"
    goodipzone = "domain.org.tld/ANOTHER_ORG/UNIX/Zones/B_GROUP_NAME"

    badipzone = "BADZONE"

    good_hostname = "qumulo-int.org.tld"
    goodip = "a.b.c.d"
    badname = "badname.org"
    badip = "1.2.3.4"
    testqsize = 123
    testdirid = 4567
    testdirid2 = 45672
    testdirid3 = 45673

    gooddnsdomain = 'domain.org.tld'
    revdnsdomain = 'tld.org.domain'
    badrevdnsdomain = 'tld.org.dmaino'
    goodexportpath = "/a/good/export/path"
    badexportpath = "/verylittlechancethispathexists"
    badorganization = "badorg"
    goodorganization = "unknown"
    goodorganization2 = "unknown2"
    gooddc = "centrify.org.tld"
    baddc = "testdc"
    testcp = "/test/cluster/path/one/two"
    testcp2 = "/test/cluster/path2"
    testcp3 = "/test/cluster/path3"
    testqid = 98765
    testlimit = 123456789

    oneip = ['a.b.c.d']
    twoips = ['a.b.c.d', 'a.b.c.e']
    threeips = ['a.b.c.d', 'a.b.c.e', 'f.g.h.i']



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

###############################################################################################################
#    ____  _   _ ____      _                       _       __  __           _       _ _____         _         #
#   |  _ \| \ | / ___|  __| | ___  _ __ ___   __ _(_)_ __ |  \/  | ___   __| | ___ | |_   _|__  ___| |_ ___   #
#   | | | |  \| \___ \ / _` |/ _ \| '_ ` _ \ / _` | | '_ \| |\/| |/ _ \ / _` |/ _ \| | | |/ _ \/ __| __/ __|  #
#   | |_| | |\  |___) | (_| | (_) | | | | | | (_| | | | | | |  | | (_) | (_| |  __/| | | |  __/\__ \ |_\__ \  #
#   |____/|_| \_|____/ \__,_|\___/|_| |_| |_|\__,_|_|_| |_|_|  |_|\___/ \__,_|\___||_| |_|\___||___/\__|___/  #
#                                                                                                             #
###############################################################################################################

class DNSDomainModelTests(TestCase):
    def test_get_windcs_zero(self):
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dcs = dnsd.get_dcs_from_msdcs()
        self.assertIs(len(dcs) == 1, True)

    def test_get_windcs(self):
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dcs = dnsd.get_dcs_from_msdcs()
        self.assertIs(len(dcs) > 1, True)

    def test_check_dcs_bad(self):
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dcs = dnsd.get_dcs_from_msdcs()
        self.assertIs(len(dcs) == 1, True)

    def test_check_dcs(self):
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dcs = dnsd.get_dcs_from_msdcs()
        self.assertIs(len(dcs) > 1, True)

    def test_get_dcs_from_msdcs_bad(self):
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dcs = dnsd.get_dcs_from_msdcs()
        self.assertIs(len(dcs) == 1, True)

    def test_get_dcs_from_msdcs(self):
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dcs = dnsd.get_dcs_from_msdcs()
        self.assertIs(len(dcs) > 1, True)


#########################################################################################################################################################
#     ___                        _          _   _             _____          _            _           __  __           _      _ _____         _         #
#    / _ \ _ __ __ _  __ _ _ __ (_)______ _| |_(_) ___  _ __ | ____|_  _____| | _   _  __| | ___  ___|  \/  | ___   __| | ___| |_   _|__  ___| |_ ___   #
#   | | | | '__/ _` |/ _` | '_ \| |_  / _` | __| |/ _ \| '_ \|  _| \ \/ / __| || | | |/ _` |/ _ \/ __| |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __/ __|  #
#   | |_| | | | (_| | (_| | | | | |/ / (_| | |_| | (_) | | | | |___ >  < (__| || |_| | (_| |  __/\__ \ |  | | (_) | (_| |  __/ | | |  __/\__ \ |_\__ \  #
#    \___/|_|  \__, |\__,_|_| |_|_/___\__,_|\__|_|\___/|_| |_|_____/_/\_\___|_| \__,_|\__,_|\___||___/_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__|___/  #
#              |___/                                                                                                                                    #
#########################################################################################################################################################

class OrganizationExcludesModelTests(TestCase):
    def test_get_excludes(self):
        """
        get_excludes returns list of 'organizations' to exclude.  'UNIX' is at the end of the list.
        """
        testoe = OrganizationExcludes()
        self.assertIn('UNIX', testoe.get_excludes())

    def testset_excludes(self):
        '''
        sets the list of excluded organizations
        :param exlist: space delimited list of organizations
        :return: no return value
        '''
        exlist = ['test string ']
        testoe = OrganizationExcludes()
        testoe.set_excludes(exlist)
        self.assertIn('UNIX', testoe.get_excludes())

    def add_excludes(self):
        '''
        adds list of excluded organizations
        :param addlist: space delimited list of organizations to be appended to existing list
        :return: no return value
        '''
        addlist = ['test string ']
        testoe = OrganizationExcludes()
        testoe.add_excludes(addlist)
        self.assertIn('UNIX', testoe.get_excludes())

    def delete_excludes(self):
        '''
        removes a list of organizations from the existing list
        :param dellist:
        :return:
        '''
        dellist = ['test string ']
        testoe = OrganizationExcludes()
        testoe.delete_excludes(dellist)
        self.assertIn('UNIX', testoe.get_excludes())


########################################################################################
#     ____ _           _            __  __           _      _ _____         _          #
#    / ___| |_   _ ___| |_ ___ _ __|  \/  | ___   __| | ___| |_   _|__  ___| |_  ___   #
#   | |   | | | | / __| __/ _ \ '__| |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __|/ __|  #
#   | |___| | |_| \__ \ ||  __/ |  | |  | | (_) | (_| |  __/ | | |  __/\__ \ |_ \__ \  #
#    \____|_|\__,_|___/\__\___|_|  |_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__||___/  #
#                                                                                      #
########################################################################################

class ClusterModelTests(TestCase):
    def test_alive_badip(self):
        ## expected to return false
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.badip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        self.assertIs(testc.alive(), False)

    def test_alive_socket_error(self):
        ## expected to return false
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.badip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        self.assertIs(testc.alive(), False)

    def test_alive_goodcluster(self):
        ## expected to return true
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        self.assertIs(testc.alive(), True)

    def test_create_directory_on_cluster(self):
        ## expected to return a non-zero 'path id' which references the directory created
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        (conninfo, creds) = qlogin(testc.ipaddr, testc.adminname, testc.adminpassword, testc.port)
        did = testc.create_directory_on_cluster(conninfo, creds, Testparams.testcp)
        ok = False
        if did > 0:
            ok = True
        self.assertIs(ok, True)

    def test_delete_directory_on_cluster(self):
        ## return message includes 'deleted directory' if the deletion was successful
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        (conninfo, creds) = qlogin(testc.ipaddr, testc.adminname, testc.adminpassword, testc.port)
        msg = testc.delete_directory_on_cluster(conninfo, creds, Testparams.testcp)
        ok = False
        if 'deleted directory' in msg:
            ok = True
        self.assertIs(ok, True)

    def test_create_quota_on_cluster(self):
        ## expected to return 'created quota' in msg
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        (conninfo, creds) = qlogin(testc.ipaddr, testc.adminname, testc.adminpassword, testc.port)
        did = testc.create_directory_on_cluster(conninfo, creds, Testparams.testcp)
        msg = testc.create_quota_on_cluster(conninfo, creds, did, Testparams.testcp, Testparams.testlimit)
        ok = False
        if 'created quota_' in msg:
            ok = True
        self.assertIs(ok, True)

    def test_delete_quota_on_cluster(self):
        ## expected to return deleted_quota is msg
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        (conninfo, creds) = qlogin(testc.ipaddr, testc.adminname, testc.adminpassword, testc.port)

        did = testc.create_directory_on_cluster(conninfo, creds, Testparams.testcp)
        msg = testc.create_quota_on_cluster(conninfo, creds, did, Testparams.testcp, Testparams.testlimit)
        # print(msg)
        msg = testc.delete_quota_on_cluster(conninfo, creds, did, Testparams.testcp)
        #print(msg)
        ok = False
        if 'deleted quota_' in msg:
            ok = True
        self.assertIs(ok, True)

    def test_fetch_clusterpaths_goodcluster(self):
        ## expect one or more items in returned list of quotas
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        (conninfo, creds) = qlogin(testc.ipaddr, testc.adminname, testc.adminpassword, testc.port)
        did = testc.create_directory_on_cluster(conninfo, creds, Testparams.testcp)
        msg = testc.create_quota_on_cluster(conninfo, creds, did, Testparams.testcp, Testparams.testlimit)
        quotas = testc.fetch_qumulo_shares(testc)
        #msg = testc.delete_quota_on_cluster(conninfo, creds, did, Testparams.testcp)
        self.assertIs(len(quotas) > 0, True)

    def test_sync_clusterpaths_from_cluster_goodcluster(self):
        # length of activity['out_of_sync'] should be 0
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        activity = testc.sync_clusterpaths_from_cluster(testc)
        self.assertIs(len(activity['out_of_sync']) == 0, True)

    def test_sync_clusterpaths_to_cluster_goodcluster(self):
        # length of activity['out_of_sync'] should be 0
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        activity = testc.sync_clusterpaths_to_cluster(testc)
        self.assertIs(len(activity['out_of_sync']) == 0, True)

    def test_fetch_nfs_shares_goodcluster(self):
        # expect one or more items in returned list of shares
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        shares = testc.fetch_nfs_shares(testc)
        self.assertIs(len(shares) > 0, True)

    def test_sync_nfs_exports_from_cluster_goodcluster(self):
        # length of activity['out_of_sync'] should be 0
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        activity = testc.sync_nfs_exports_from_cluster(testc)
        self.assertIs(len(activity['out_of_sync']) == 0, True)

    def test_host_restrictions_to_ipaddrlist_blanklist(self):
        ## state expected to be True
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        restrictions = ""
        ipaddrlist = testc.host_restrictions_to_ipaddrlist(restrictions)
        self.assertIs(len(ipaddrlist) == 0, True)

    def test_host_restrictions_to_ipaddrlist_comma_delimited_list(self):
        ## state expected to be True
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        restrictions = [
            "137.75.200.204",
            "137.75.200.203"]
        ipaddrlist = testc.host_restrictions_to_ipaddrlist(restrictions)
        self.assertIs(len(ipaddrlist) == 2, True)

    # https://en.wikipedia.org/wiki/Subnetwork
    def test_host_restrictions_to_ipaddrlist_slash25(self):
        ## state expected to be True
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        restrictions = ["192.168.0.0/25"]
        ipaddrlist = testc.host_restrictions_to_ipaddrlist(restrictions)
        self.assertIs(len(ipaddrlist) == 126, True)

    def test_host_restrictions_to_ipaddrlist_slash255255255000(self):
        ## expect 256 hosts
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        restrictions = ["192.168.0.0/255.255.255.0"]
        ipaddrlist = testc.host_restrictions_to_ipaddrlist(restrictions)
        self.assertIs(len(ipaddrlist) == 254, True)

    def test_host_restrictions_to_ipaddrlist_dash10(self):
        ## expect ? hosts
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword)
        testc.save()
        restrictions = ["192.168.1.1-10"]
        ipaddrlist = testc.host_restrictions_to_ipaddrlist(restrictions)
        self.assertIs(len(ipaddrlist) == 10, True)


###################################################################################
#     ___              _        __  __           _      _ _____         _         #
#    / _ \ _   _  ___ | |_ __ _|  \/  | ___   __| | ___| |_   _|__  ___| |_ ___   #
#   | | | | | | |/ _ \| __/ _` | |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __/ __|  #
#   | |_| | |_| | (_) | || (_| | |  | | (_) | (_| |  __/ | | |  __/\__ \ |_\__ \  #
#    \__\_\\__,_|\___/ \__\__,_|_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__|___/  #
#                                                                                 #
###################################################################################

class QuotaModelTests(TestCase):
    def test_get_size(self):
        """
        get_size should return the quota's size
        """
        testq = Quota(qid=1, name="test", size=Testparams.testqsize)
        testq.save()
        self.assertEqual(testq.get_size(), Testparams.testqsize)

##############################################################################################################
#     ____ _           _                        _   _     __  __           _       _ _____         _         #
#    / ___| |_   _ ___| |_ ___ _ __ _ __   __ _| |_| |__ |  \/  | ___   __| | ___ | |_   _|__  ___| |_ ___   #
#   | |   | | | | / __| __/ _ \ '__| '_ \ / _` | __| '_ \| |\/| |/ _ \ / _` |/ _ \| | | |/ _ \/ __| __/ __|  #
#   | |___| | |_| \__ \ ||  __/ |  | |_) | (_| | |_| | | | |  | | (_) | (_| |  __/| | | |  __/\__ \ |_\__ \  #
#    \____|_|\__,_|___/\__\___|_|  | .__/ \__,_|\__|_| |_|_|  |_|\___/ \__,_|\___||_| |_|\___||___/\__|___/  #
#                                  |_|                                                                       #
##############################################################################################################

# class ClusterpathModelTests(TestCase):
#    def test_get_dirid(self):
#        """
#        get_dirid should return the cluster path's directory id
#        """
#        testc = Cluster(dirpath=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
#                        adminpassword=Testparams.goodclusteradminpassword, )
#        testc.save()
#        testq = Quota(dirpath="testq", size=Testparams.testqsize)
#        testq.save()
#        testcp = Clusterpath(dirpath='testcp', cluster=testc, quota=testq, exportid=Testparams.testdirid)
#        testcp.save()
#        self.assertIs(testcp.get_dirid() == Testparams.testdirid, True)


############################################################################
#    _   _           _   __  __           _      _ _____         _         #
#   | | | | ___  ___| |_|  \/  | ___   __| | ___| |_   _|__  ___| |_ ___   #
#   | |_| |/ _ \/ __| __| |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __/ __|  #
#   |  _  | (_) \__ \ |_| |  | | (_) | (_| |  __/ | | |  __/\__ \ |_\__ \  #
#   |_| |_|\___/|___/\__|_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__|___/  #
#                                                                          #
############################################################################

class HostModelTests(TestCase):
    def test_check_hostname_allok(self):
        """
        check_hostname returns false if the dirpath was not updated
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save
        testhost = Host(name=Testparams.good_hostname, ipaddr=Testparams.goodip, ipzone=testipz)
        testhost.save
        self.assertIs(testhost.check_hostname(), False)

    def test_check_hostip_allok(self):
        """
        check_hostip returns false if the ipaddress was not updated
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testhost = Host(name=Testparams, ipaddr=Testparams.goodip, ipzone=testipz)
        testhost.save()
        self.assertIs(testhost.check_hostip(), True)

    def test_check_hostname_badipaddr(self):
        """
        check_hostname returns true if the host was upddated
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testhost = Host(name=Testparams.good_hostname, ipaddr=Testparams.badip, ipzone=testipz)
        testhost.save()
        self.assertIs(testhost.check_hostname(), True)

    def test_check_hostip_badhostname(self):
        """
        check_hostip returns true if the ipaddress was updated
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testhost = Host(name=Testparams.badname, ipaddr=Testparams.goodip, ipzone=testipz)
        testhost.save()
        print("testhost is " + str(testhost))
        print("    ipaddr is: " + str(testhost.ipaddr))
        checkresult = testhost.check_hostip()
        print("checkresult: " + str(checkresult))
        self.assertIs(checkresult, True)

##################################################################################################################
#     ___                        _          _   _             __  __           _       _ _____         _         #
#    / _ \ _ __ __ _  __ _ _ __ (_)______ _| |_(_) ___  _ __ |  \/  | ___   __| |  ___| |_   _|__  ___| |_ ___   #
#   | | | | '__/ _` |/ _` | '_ \| |_  / _` | __| |/ _ \| '_ \| |\/| |/ _ \ / _` | / _ \ | | |/ _ \/ __| __/ __|  #
#   | |_| | | | (_| | (_| | | | | |/ / (_| | |_| | (_) | | | | |  | | (_) | (_| ||  __/ | | |  __/\__ \ |_\__ \  #
#    \___/|_|  \__, |\__,_|_| |_|_/___\__,_|\__|_|\___/|_| |_|_|  |_|\___/ \__,_| \___|_| |_|\___||___/\__|___/  #
#              |___/                                                                                             #
##################################################################################################################

class OrganizationModelTests(TestCase):
    #    dirpath = models.CharField(max_length=50, null=True, default='')
    #    ipzone = []
    #    hosts = []
    #    clusterpaths = models.ForeignKey(Clusterpath, on_delete=models.CASCADE)
    #    updated = models.DateTimeField(auto_now_add=True)

    def test_get_ipzones_from_windc(self):
        """
        get_ipzones_from_windc returns a non-zero length length of zones
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testorg.set_ipzones([testipz])
        testcp.set_organization(testorg)
        testdns = DNSdomain(name=Testparams.gooddnsdomain)
        testdns.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=testdns)
        wdc.save()
        wdc.set_ipzones([testipz])
        ipzones = testorg.get_ipzones_from_windc()
        self.assertIs(len(ipzones) > 0, True)

    def test_get_hosts_from_windc(self):
        """
        get_hosts_from_windc returns a non-zero length length of hosts
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testorg.set_hosts([Testparams.goodip])
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testorg.set_ipzones([testipz])
        testcp.set_organization(testorg)
        testdns = DNSdomain(name=Testparams.gooddnsdomain)
        testdns.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=testdns)
        wdc.save()
        wdc.set_ipzones([testipz])
        state = wdc.load_newhosts()
        activity = wdc.sync_ips_in_all_WinDCs()
        hosts = testorg.get_hosts_from_windc()
        self.assertIs(len(hosts) > 0, True)

    def test_check_ipzones(self):
        """
        load_newipzones returns true if new zones were added
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testorg.set_ipzones([testipz])
        testdns = DNSdomain(name=Testparams.gooddnsdomain)
        testdns.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=testdns)
        wdc.save()
        wdc.set_ipzones([testipz])
        activity = testorg.check_ipzones()
        self.assertIs(len(activity['newzones']) > 0, True)

    def test_check_hosts(self):
        """
        load_newhosts returns true if new hosts were added
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testorg.set_ipzones([testipz])
        testdns = DNSdomain(name=Testparams.gooddnsdomain)
        testdns.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=testdns)
        wdc.save()
        wdc.set_ipzones([testipz])
        activity = testorg.check_hosts()
        self.assertIs(len(activity['newhosts']) > 0, True)

    def test_get_ipzones(self):
        """
        get_ipzone returns a non-zero length length of zones
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testorg.set_ipzones([testipz])
        testcp.set_organization(testorg)
        testdns = DNSdomain(name=Testparams.gooddnsdomain)
        testdns.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=testdns)
        wdc.save()
        wdc.set_ipzones([testipz])
        testorg.check_ipzones()
        ipzones = testorg.get_ipzones()
        self.assertIs(len(ipzones) > 0, True)

    def test_get_hosts(self):
        """
        get_hosts returns a non-zero length length of hosts
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testorg.set_hosts([Testparams.goodip])
        testcp.set_organization(testorg)
        hosts = testorg.get_hosts()
        self.assertIs(len(hosts) > 0, True)

    def test_get_adminhosts(self):
        """
        get_hosts returns a non-zero length length of hosts
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testorg.set_adminhosts([Testparams.goodip])
        testcp.set_organization(testorg)
        hosts = testorg.get_adminhosts()
        self.assertIs(len(hosts) > 0, True)

    def test_set_clusterpaths_one(self):
        """
        test for one clusterpath
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        qr = Organization.objects.filter(name=Testparams.goodorganization)
        cpcount = qr[0].clusterpaths.count()
        self.assertIs(cpcount == 1, True)

    def test_set_clusterpaths_three(self):
        """
        test for three clusterpaths
        """
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testcp2 = Clusterpath(dirpath=Testparams.testcp2, cluster=testc, quota=testq, dirid=Testparams.testdirid2)
        testcp2.save()
        testcp3 = Clusterpath(dirpath=Testparams.testcp3, cluster=testc, quota=testq, dirid=Testparams.testdirid3)
        testcp3.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp, testcp2, testcp3])
        testcp.set_organization(testorg)
        qr = Organization.objects.filter(name=Testparams.goodorganization)
        cpcount = qr[0].clusterpaths.count()
        self.assertIs(cpcount == 3, True)


######################################################################################
#    ___ ____                      __  __           _      _ _____         _         #
#   |_ _|  _ \ _______  _ __   ___|  \/  | ___   __| | ___| |_   _|__  ___| |_ ___   #
#    | || |_) |_  / _ \| '_ \ / _ \ |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __/ __|  #
#    | ||  __/ / / (_) | | | |  __/ |  | | (_) | (_| |  __/ | | |  __/\__ \ |_\__ \  #
#   |___|_|   /___\___/|_| |_|\___|_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__|___/  #
#                                                                                    #
######################################################################################

class ADzoneModelTests(TestCase):
    #    dirpath = models.CharField('ADZone', max_length=250)
    #    ipaddrs = []
    #    quota = models.ForeignKey(Quota, on_delete=models.CASCADE)
    #    organization = models.CharField('Organization', max_length=250, default='unknown')
    #    updated = models.DateTimeField(auto_now_add=True)

    def test_get_ipddrs_empty(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        self.assertIs(len(testipz.get_ipaddrs()) > 0, False)

    def test_get_ipddrs(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq, )
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        iplist = []
        iplist.append(Testparams.goodclusterip)
        iplist.append(Testparams.badip)
        iplist.append(Testparams.goodip)
        testipz.set_ipaddrs(iplist)
        testipz.save()
        ipadddirs = testipz.get_ipaddrs()
        self.assertIs(len(ipadddirs) == 3, True)


#########################################################################################################
#    _   _  __     _____                       _   __  __           _      _ _____            _         #
#   | \ | |/ _|___| ____|_  ___ __   ___  _ __| |_|  \/  | ___   __| | ___| |_   _|  ___  ___| |_ ___   #
#   |  \| | |_/ __|  _| \ \/ / '_ \ / _ \| '__| __| |\/| |/ _ \ / _` |/ _ \ | | |   / _ \/ __| __/ __|  #
#   | |\  |  _\__ \ |___ >  <| |_) | (_) | |  | |_| |  | | (_) | (_| |  __/ | | |  |  __/\__ \ |_\__ \  #
#   |_| \_|_| |___/_____/_/\_\ .__/ \___/|_|   \__|_|  |_|\___/ \__,_|\___|_| |_|   \___||___/\__|___/  #
#                            |_|                                                                        #
#########################################################################################################

class NfsExportModelTests(TestCase):

    def test_set_restrictions(self):
        # self.restrictions.all().delete()
        # for r in rlist:
        #    self.restrictions.add(r)
        # self.save()
        rlist = []
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq, )
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testr1 = Restriction(name="test restriction 1", readonly=True, usermapping='None', usermapid=1)
        testr1.save()
        rlist.append(testr1)
        testr = Restriction(name="test restriction 2", readonly=True, usermapping='None', usermapid=2)
        testr.save()
        rlist.append(testr)
        self.assertEqual(len(rlist) == 2, True)

    #delete_nfsexport_on_cluster

########################################################################################
#   __        ___       ____   ____ __  __           _      _ _____         _          #
#   \ \      / (_)_ __ |  _ \ / ___|  \/  | ___   __| | ___| |_   _|__  ___| |_  ___   #
#    \ \ /\ / /| | '_ \| | | | |   | |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __|/ __|  #
#     \ V  V / | | | | | |_| | |___| |  | | (_) | (_| |  __/ | | |  __/\__ \ |_ \__ \  #
#      \_/\_/  |_|_| |_|____/ \____|_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__||___/  #
#                                                                                      #
########################################################################################

class WinDCModelTests(TestCase):
    def test_get_org_by_zone_badipz(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.badipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        org = wdc.get_orgname_by_zone(testipz)
        self.assertIs(len(org) == 0, True)

    def test_get_org_by_zone_goodipz(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        org = wdc.get_orgname_by_zone(testipz)
        self.assertIs(len(org) > 0, True)

    def test_load_neworgs_badipz(self):
        # return state
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.badipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        self.assertIs(wdc.load_neworgs(testc), False)

    def test_load_neworgs_goodipz(self):
        # return state
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        self.assertIs(wdc.load_neworgs(testc), True)

    def test_load_newipzones_badipz(self):
        # return state
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.badipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        self.assertIs(wdc.load_newipzones(), False)

    def test_load_newipzones_goodipz(self):
        # return state
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        self.assertIs(wdc.load_newipzones(), True)

    def test_load_newhosts_baddomain(self):
        # return state
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        self.assertIs(wdc.load_newhosts(), False)

    def test_load_newhosts_gooddomain(self):
        # return state
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirid=Testparams.testdirid, dirpath=Testparams.testcp, cluster=testc, quota=testq)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        self.assertIs(wdc.load_newhosts(), True)

    def test_get_orgs_from_ldap_baddomain(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        orgs = wdc.get_orgs_from_ldap()
        self.assertIs(len(orgs) == 0, True)

    def test_get_orgs_from_ldap_gooddomain(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        print("gooddc is: " + str(Testparams.gooddc))
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        orgs = wdc.get_orgs_from_ldap()
        print("orgs: " + str(orgs))
        self.assertIs(len(orgs) > 0, True)

    def test_get_ipzones_from_ldap_baddomain(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        ipzones = wdc.get_ipzones_by_org_from_ldap()
        self.assertIs(len(ipzones) == 0, True)

    def test_get_ipzones_from_ldap_gooddomain(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        ipzones = wdc.get_ipzones_by_org_from_ldap()
        print("ipzones: " + str(ipzones))
        self.assertIs(len(ipzones) > 0, True)

    def test_get_hosts_by_ipzone_from_ldap_baddomain(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.badrevdnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        hosts = wdc.get_hosts_by_ipzone_from_ldap()
        self.assertIs(len(hosts) == 0, True)

    def test_get_hosts_by_ipzone_from_ldap_gooddomain(self):
        # return org
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        dnsd = DNSdomain(name=Testparams.gooddnsdomain)
        dnsd.save()
        wdc = WinDC(name=Testparams.gooddc, dnsdomain=dnsd)
        wdc.save()
        wdc.set_ipzones([testipz])
        hosts = wdc.get_hosts_by_ipzone_from_ldap()
        self.assertIs(len(hosts) > 0, True)


########################################################################################
#    ____                       _   __  __           _      _ _____         _          #
#   |  _ \ ___ _ __   ___  _ __| |_|  \/  | ___   __| | ___| |_   _|__  ___| |_  ___   #
#   | |_) / _ \ '_ \ / _ \| '__| __| |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __|/ __|  #
#   |  _ <  __/ |_) | (_) | |  | |_| |  | | (_) | (_| |  __/ | | |  __/\__ \ |_ \__ \  #
#   |_| \_\___| .__/ \___/|_|   \__|_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__||___/  #
#             |_|                                                                      #
########################################################################################

class ReportModelTests(TestCase):

    def test_get_cadence(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        rpt = Report(name='testreport', organization=testorg, type="testtype1", cadence=Testparams.testdirid)
        self.assertEqual(rpt.get_cadence() == Testparams.testdirid, True)


##########################################################################################################
#    ____           _        _      _   _             __  __           _      _  _____         _         #
#   |  _ \ ___  ___| |_ _ __(_) ___| |_(_) ___  _ __ |  \/  | ___   __| | ___| ||_   _|__  ___| |_ ___   #
#   | |_) / _ \/ __| __| '__| |/ __| __| |/ _ \| '_ \| |\/| |/ _ \ / _` |/ _ \ |  | |/ _ \/ __| __/ __|  #
#   |  _ <  __/\__ \ |_| |  | | (__| |_| | (_) | | | | |  | | (_) | (_| |  __/ |  | |  __/\__ \ |_\__ \  #
#   |_| \_\___||___/\__|_|  |_|\___|\__|_|\___/|_| |_|_|  |_|\___/ \__,_|\___|_|  |_|\___||___/\__|___/  #
#                                                                                                        #
##########################################################################################################

class RestrictionModelTests(TestCase):

    def test_get_ipzones(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        lh = Host(name="None", ipaddr='0.0.0.0', ipzone_id=testipz.id)
        lh.save()
        testr = Restriction(name="test restriction", readonly=True, usermapping='None', usermapid=1)
        testr.save()
        testr.ipzones.add(testipz)
        testr.save()
        ipzones = str(testr.get_ipzones())
        self.assertIs(len(ipzones) > 0, True)

    def test_get_all_ipzone_ipaddrs_onezone_twoips(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testipz.set_ipaddrs(Testparams.twoips)
        testr = Restriction(name="test restriction", readonly=True, usermapping='None', usermapid=1)
        testr.save()
        testr.ipzones.add(testipz)
        testr.save()
        ipaddrs = testr.get_all_ipzone_ipaddrs()
        self.assertIs(len(ipaddrs) == 2, True)

    def test_get_all_ipzone_ipaddrs_twozones_z1oneip_z2threeips(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testipz.set_ipaddrs(Testparams.twoips)
        testipz2 = IPzone(name=Testparams.goodipzone2, organization=testorg)
        testipz2.save()
        testipz2.set_ipaddrs(Testparams.threeips)
        testr = Restriction(name="test restriction", readonly=True, usermapping='None', usermapid=1)
        testr.save()
        testr.ipzones.add(testipz)
        testr.ipzones.add(testipz2)
        testr.save()
        ipaddrs = testr.get_all_ipzone_ipaddrs()
        self.assertIs(len(ipaddrs) == 5, True)

    def test_set_ipzone_ipaddrs_onezone_twoips(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testipz.set_ipaddrs(Testparams.twoips)
        testr = Restriction(name="test restriction", readonly=True, usermapping='None', usermapid=1)
        testr.save()
        testr.ipzones.add(testipz)
        testr.save()
        testr.set_ipzone_ipaddrs(str(testipz), Testparams.twoips)
        ipaddrs = testr.get_all_ipzone_ipaddrs()
        self.assertIs(len(ipaddrs) == 2, True)

    def test_set_ipzone_ipaddrs_twozones_twoips(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testipz.set_ipaddrs(Testparams.twoips)
        testipz2 = IPzone(name=Testparams.goodipzone2, organization=testorg)
        testipz2.save()
        testipz2.set_ipaddrs(Testparams.threeips)
        testr = Restriction(name="test restriction", readonly=True, usermapping='None', usermapid=1)
        testr.save()
        # add two
        testr.ipzones.add(testipz)
        # add three others
        testr.ipzones.add(testipz2)
        testr.save()
        # replace first two the three others
        testr.set_ipzone_ipaddrs(str(testipz), Testparams.threeips)
        ipaddrs = testr.get_all_ipzone_ipaddrs()
        print("  ipaddrs: " + str(ipaddrs))
        # should get only three
        self.assertIs(len(ipaddrs) == 3, True)

    def test_get_all_individual_ipaddrs(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testcp.set_organization(testorg)
        testipz = IPzone(name=Testparams.goodipzone, organization=testorg)
        testipz.save()
        testipz.set_ipaddrs(Testparams.twoips)
        testr = Restriction(name="test restriction", readonly=True, usermapping='None', usermapid=1)
        testr.save()
        testhost = Host(name=Testparams.good_hostname, ipaddr=Testparams.goodip, ipzone=testipz)
        testhost.save()
        testr.individual_hosts.add(testhost)
        ipaddrs = testr.get_all_individual_ipaddrs()
        print("  ipaddrs: " + str(ipaddrs))
        # should get one
        self.assertIs(len(ipaddrs) == 1, True)

#########################################################################################################
#    ____                      _           _       __  __           _      _ _____            _         #
#   / ___| _   _ ___  __ _  __| |_ __ ___ (_)_ __ |  \/  | ___   __| | ___| |_   _|  ___  ___| |_ ___   #
#   \___ \| | | / __|/ _` |/ _` | '_ ` _ \| | '_ \| |\/| |/ _ \ / _` |/ _ \ | | |   / _ \/ __| __/ __|  #
#    ___) | |_| \__ \ (_| | (_| | | | | | | | | | | |  | | (_) | (_| |  __/ | | |  |  __/\__ \ |_\__ \  #
#   |____/ \__, |___/\__,_|\__,_|_| |_| |_|_|_| |_|_|  |_|\___/ \__,_|\___|_| |_|   \___||___/\__|___/  #
#          |___/                                                                                        #
#########################################################################################################

class SysadminModelTests(TestCase):

    def test_get_organizations(self):
        testc = Cluster(name=Testparams.goodclustername, ipaddr=Testparams.goodclusterip,
                        adminpassword=Testparams.goodclusteradminpassword, )
        testc.save()
        testq = Quota(qid=1, name="testq", size=Testparams.testqsize)
        testq.save()
        testcp = Clusterpath(dirpath=Testparams.testcp, cluster=testc, quota=testq, dirid=Testparams.testdirid)
        testcp.save()
        testorg = Organization(name=Testparams.goodorganization)
        testorg.save()
        testorg.set_clusterpaths([testcp])
        testorg2 = Organization(name=Testparams.goodorganization2)
        testorg2.save()
        testorg2.set_clusterpaths([testcp])
        testorgs = []
        testorgs.append(testorg)
        testorgs.append(testorg2)
        testcp.set_organization(testorg)
        sadm = Sysadmin(name='dilbert')
        sadm.save()
        sadm.organizations.add(testorg)
        sadm.organizations.add(testorg2)
        retorgs = []
        orgs = sadm.get_organizations()
        for o in orgs:
            retorgs.append(o)
        self.assertEqual(retorgs, testorgs)

#############################################################################################
#       _        _   _       _ _         __  __           _      _ _____          _         #
#      / \   ___| |_(_)_   _(_) |_ _   _|  \/  | ___   __| | ___| |_   _|__  ___ | |_ ___   #
#     / _ \ / __| __| \ \ / / | __| | | | |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __|| __/ __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| | |  | | (_) | (_| |  __/ | | |  __/\__ \| |_\__ \  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |_|  |_|\___/ \__,_|\___|_| |_|\___||___/ \__|___/  #
#                                  |___/                                                    #
#############################################################################################


##############################################################################################################
#     ___              _        _____                 _   __  __           _       _ _____         _         #
#    / _ \ _   _  ___ | |_ __ _| ____|_   _____ _ __ | |_|  \/  | ___   __| | ___ | |_   _|__  ___| |_ ___   #
#   | | | | | | |/ _ \| __/ _` |  _| \ \ / / _ \ '_ \| __| |\/| |/ _ \ / _` |/ _ \| | | |/ _ \/ __| __/ __|  #
#   | |_| | |_| | (_) | || (_| | |___ \ V /  __/ | | | |_| |  | | (_) | (_| |  __/| | | |  __/\__ \ |_\__ \  #
#    \__\_\\__,_|\___/ \__\__,_|_____| \_/ \___|_| |_|\__|_|  |_|\___/ \__,_|\___||_| |_|\___||___/\__|___/  #
#                                                                                                            #
##############################################################################################################


##########################################################################################################
#     ____ _           _            ____  _       _   __  __           _      _  _____         _         #
#    / ___| |_   _ ___| |_ ___ _ __/ ___|| | ___ | |_|  \/  | ___   __| | ___| ||_   _|__  ___| |_ ___   #
#   | |   | | | | / __| __/ _ \ '__\___ \| |/ _ \| __| |\/| |/ _ \ / _` |/ _ \ |  | |/ _ \/ __| __/ __|  #
#   | |___| | |_| \__ \ ||  __/ |   ___) | | (_) | |_| |  | | (_) | (_| |  __/ |  | |  __/\__ \ |_\__ \  #
#    \____|_|\__,_|___/\__\___|_|  |____/|_|\___/ \__|_|  |_|\___/ \__,_|\___|_|  |_|\___||___/\__|___/  #
#                                                                                                        #
##########################################################################################################

################################################################################################################
#       _        _   _       _ _         ____  _        _   __  __           _       _ _____         _         #
#      / \   ___| |_(_)_   _(_) |_ _   _/ ___|| |_ __ _| |_|  \/  | ___   __| |  ___| |_   _|__  ___| |_ ___   #
#     / _ \ / __| __| \ \ / / | __| | | \___ \| __/ _` | __| |\/| |/ _ \ / _` | / _ \ | | |/ _ \/ __| __/ __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |___) | || (_| | |_| |  | | (_) | (_| ||  __/ | | |  __/\__ \ |_\__ \  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |____/ \__\__,_|\__|_|  |_|\___/ \__,_| \___|_| |_|\___||___/\__|___/  #
#                                  |___/                                                                       #
################################################################################################################

######################################################################################################################################################
#       _        _   _       _ _         ____                    _              ____  _        _   __  __           _      _ _____         _         #
#      / \   ___| |_(_)_   _(_) |_ _   _|  _ \ _   _ _ __  _ __ (_)_ __   __ _ / ___|| |_ __ _| |_|  \/  | ___   __| | ___| |_   _|__  ___| |_ ___   #
#     / _ \ / __| __| \ \ / / | __| | | | |_) | | | | '_ \| '_ \| | '_ \ / _` |\___ \| __/ _` | __| |\/| |/ _ \ / _` |/ _ \ | | |/ _ \/ __| __/ __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |  _ <| |_| | | | | | | | | | | | (_| | ___) | || (_| | |_| |  | | (_) | (_| |  __/ | | |  __/\__ \ |_\__ \  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |_| \_\\__,_|_| |_|_| |_|_|_| |_|\__, ||____/ \__\__,_|\__|_|  |_|\___/ \__,_|\___|_| |_|\___||___/\__|___/  #
#                                  |___/                                 |___/                                                                       #
######################################################################################################################################################

####################################################################################################################
#       _        _   _       _ _         _____    _       _     __  __           _       _ _____         _         #
#      / \   ___| |_(_)_   _(_) |_ _   _|  ___|__| |_ ___| |__ |  \/  | ___   __| |  ___| |_   _|__  ___| |_ ___   #
#     / _ \ / __| __| \ \ / / | __| | | | |_ / _ \ __/ __| '_ \| |\/| |/ _ \ / _` | / _ \ | | |/ _ \/ __| __/ __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| |  _|  __/ || (__| | | | |  | | (_) | (_| ||  __/ | | |  __/\__ \ |_\__ \  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, |_|  \___|\__\___|_| |_|_|  |_|\___/ \__,_| \___|_| |_|\___||___/\__|___/  #
#                                  |___/                                                                           #
####################################################################################################################

##################################################################################################################
#       _        _   _       _ _        _____                 __  __           _       _ _____         _         #
#      / \   ___| |_(_)_   _(_) |_ _   |_   _|   _ _ __   ___|  \/  | ___   __| |  ___| |_   _|__  ___| |_ ___   #
#     / _ \ / __| __| \ \ / / | __| | | || || | | | '_ \ / _ \ |\/| |/ _ \ / _` | / _ \ | | |/ _ \/ __| __/ __|  #
#    / ___ \ (__| |_| |\ V /| | |_| |_| || || |_| | |_) |  __/ |  | | (_) | (_| ||  __/ | | |  __/\__ \ |_\__ \  #
#   /_/   \_\___|\__|_| \_/ |_|\__|\__, ||_| \__, | .__/ \___|_|  |_|\___/ \__,_| \___|_| |_|\___||___/\__|___/  #
#                                  |___/     |___/|_|                                                            #
##################################################################################################################


###########################################################################################################################
#    ____                  ___       ____        _                 _   __  __            _      _ _____         _         #
#   |  _ \  __ _ _   _ ___|_ _|_ __ |  _ \  __ _| |_ __ _ ___  ___| |_|  \/  |  ___   __| | ___| |_   _|__  ___| |_ ___   #
#   | | | |/ _` | | | / __|| || '_ \| | | |/ _` | __/ _` / __|/ _ \ __| |\/| | / _ \ / _` |/ _ \ | | |/ _ \/ __| __/ __|  #
#   | |_| | (_| | |_| \__ \| || | | | |_| | (_| | || (_| \__ \  __/ |_| |  | || (_) | (_| |  __/ | | |  __/\__ \ |_\__ \  #
#   |____/ \__,_|\__, |___/___|_| |_|____/ \__,_|\__\__,_|___/\___|\__|_|  |_| \___/ \__,_|\___|_| |_|\___||___/\__|___/  #
#                |___/                                                                                                    #
###########################################################################################################################

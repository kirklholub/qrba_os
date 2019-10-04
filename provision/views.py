# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.views import generic
from django.contrib.auth import get_user_model
from django.forms import modelformset_factory
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.html import format_html
User = get_user_model()

from .models import NfsExport, Sysadmin, Clusterpath, Organization, Host, IPzone
from .forms import NfsExportForm
from qrba import settings
import os
import json
import re

def index(request):
    return HttpResponse("Hello, world. You're at nfs index")


def metadata(request, xid):
    xid = int(xid)
    if xid == int(0):
        qr = NfsExport.objects.all()
    else:
        qr = NfsExport.objects.filter(exportid=xid)
    metadata = {}
    metadata['admins'] = []
    orgid = int(-1)
    for export in qr:
        metadata['exportid'] = int(str(export.exportid))
        metadata['org'] = str(export.organization)
        metadata['exportpath'] = str(export.exportpath)
        metadata['creator'] = str(export.creator)
        metadata['updater'] = str(export.updater)

        restrictions = export.get_restrictions()
        metadata['restrictions'] = {}
        rnames = set()
        for r in restrictions:
            metadata['restrictions'][int(r.id)] = {}
            metadata['restrictions'][int(r.id)]['rname'] = str(r)
            rnames.add(str(r))
            metadata['restrictions'][int(r.id)]['readonly'] = str(r.readonly)
            metadata['restrictions'][int(r.id)]['ipzones'] = {}
            metadata['restrictions'][int(r.id)]['creator'] = str(r.creator)
            metadata['restrictions'][int(r.id)]['updater'] = str(r.updater)
            for ipz in r.get_ipzones():
                metadata['restrictions'][int(r.id)]['ipzones'][int(ipz.id)] = {}
                metadata['restrictions'][int(r.id)]['ipzones'][int(ipz.id)]['ipzname'] = str(ipz.name)
                metadata['restrictions'][int(r.id)]['ipzones'][int(ipz.id)]['ipzmarker'] = str(ipz.ipzmarker)
        metadata['restrictions']['rname'] = str(rnames)
        metadata['description'] = str(export.description)
        orgid = int(export.organization_id)

    sysads = Sysadmin.objects.filter(organization_id=orgid)
    alladmins = set()
    if sysads.count() > 0:
        for sysad in sysads:
            who = str(sysad)
            for user in User.objects.all():
                if str(user) == who:
                    who = str(user.email).strip().encode('ascii', 'ignore')
                    break
            alladmins.add(who)

    for sa in alladmins:
        metadata['admins'].append(sa)

    metadata = json.dumps(metadata)
    return HttpResponse(metadata)

def ipzone_from_ipzm(request, ipzm):
    qr = IPzone.objects.filter(ipzmarker=ipzm)
    metadata = {}
    for ipz in qr:
        metadata[ipz.ipzmarker] = ipz.name
    metadata = json.dumps(metadata)
    return HttpResponse(metadata)


def site_url(request):
    deploy_env = "Unknown deploy environment"
    if hasattr(settings, 'DEPLOY_ENV'):
        deploy_env = settings.DEPLOY_ENV
    else:
        local_settings_file = os.path.join(os.path.dirname(__file__), os.pardir, 'settings.py')
        if os.path.exists(local_settings_file):
            deploy_env = os.readlink(local_settings_file).split('.')[-1]

    url = settings.LOCALHOST + ":8000"

    if str(deploy_env) is 'Integration':
        url = "https://qumulo-int.org.tld/qrba"

    if str(deploy_env) is 'Production':
        url = "https://qumulo-prod.org.tld/qrba"

    return HttpResponse(url)


def all_nfsexports(request):
    opts = NfsExport.objects.all()
    return render(request, 'nfsexport/nfsexports_list.html', {'opts': opts})


def nfx_cplimit(request):
    sysad = Sysadmin.objects.filter(name=request.user)
    if sysad.count() > 0:
        org = sysad[0].organization
        form = NfsExportForm(org)
    return render(request, 'nfsexport/nfsexports_list.html', {'form': form})


class IndexView(generic.ListView):
    # template_name = 'admin/change_list.html'
    # context_object_name = 'result_list'
    model = NfsExport


class NFSExportIndexView(generic.ListView):
    template_name = 'admin/change_form.html'
    model = NfsExport

    def get_queryset(self):
        request = self.request
        sysad = Sysadmin.objects.filter(name=request.user)
        if sysad.count() > 0:
            org = sysad[0].organization
            qs = NfsExport.objects.filter(organization=org)
        else:
            qs = NfsExport.objects.all()
        pass

    def get_allow_empty(self):
        return False



class NFSExportDetailView(generic.DetailView):

    model = NfsExport

    def get_queryset(self):
        request = self.request
        sysad = Sysadmin.objects.filter(name=request.user)
        if sysad.count() > 0:
            org = sysad[0].organization
            qs = NfsExport.objects.filter(organization=org)
        else:
            qs = NfsExport.objects.all()
        pass

    def get_context_data(self, **kwargs):
        context = super(NfsExport, self).get_context_data(**kwargs)
        context['now'] = "now"
        return context

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import math
import pytz

from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.models import LogEntry

from django.contrib.auth.models import User
import logging
import datetime
import re

logger = logging.getLogger('qrba.models')
from qrba import settings
from .models import Cluster, Host, WinDC, Clusterpath, Organization, DNSdomain, IPzone, Quota, QuotaUsage, Restriction, \
    NfsExport, \
    Report, Sysadmin, Activity, QuotaEvent, ClusterSlot, ActivityStat, ActivityRunningStat, ActivityFetch, ActivityType, \
    ActivityStatComp, ConnectionType, Connection, ClusterNode, ConnectionFetch

# from .forms import NfsExportAdminForm

# for response_change and response_delete overrides
import json
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode, urlquote
from django.utils import six
from django.forms import Textarea
from django.db import models

TO_FIELD_VAR = '_to_field'
IS_POPUP_VAR = '_popup'


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
    return dt

# https://stackoverflow.com/questions/7001144/range-over-character-in-python
def char_range(c1, c2):
    """Generates the characters from `c1` to `c2`, inclusive."""
    for c in xrange(ord(c1), ord(c2) + 1):
        yield chr(c)


class ActivityTypeHostnameListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Host name starting with'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'hostletternum'

    # Custom attributes
    related_filter_parameter = 'name_istartswith'

    default_value = int(0)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """

        list_of_first_letters = []
        i = int(1)
        for c in char_range('a', 'z'):
            list_of_first_letters.append((str(i), str(c)))
            i = i + int(1)
        list_of_first_letters.append((str(i), str('137.75.')))
        return sorted(list_of_first_letters, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """

        if self.related_filter_parameter in request.GET:
            requestid = int(request.GET[self.related_filter_parameter])
            if requestid != int(0):
                fl = ''
                i = int(1)
                for c in char_range('a', 'z'):
                    if requestid == i:
                        fl = c
                        break
                    i = i + 1
                if requestid == str(27):
                    fl = '1'
                if fl != '':
                    queryset = queryset.filter(name__istartswith=fl)
        else:
            requestid = self.value()
            if requestid != str(0):
                queryset = queryset.filter(activitytype_id=requestid)
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(ActivityTypeHostnameListFilter, self).value()
        if value is None:
            if self.default_value is None:
                self.default_value = 0
            else:
                value = self.default_value
        return str(value)


class ActivityTypeListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Activity Type'
    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'type'

    default_value = int(0)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_types = []
        alltypes = ActivityType.objects.all()
        for t in alltypes:
            list_of_types.append((str(t.id), str(t)))

        return sorted(list_of_types, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """

        requestid = self.value()
        if requestid != str(0):
            queryset = queryset.filter(activitytype_id=requestid)
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(ActivityTypeListFilter, self).value()
        if value is None:
            if self.default_value is None:
                self.default_value = 0
            else:
                value = self.default_value
        return str(value)


# https://djangobook.com/customizing-change-lists-forms/
# https://www.elements.nl/blog/2015/03/16/getting-the-most-out-of-django-admin-filters/
class OrganizationListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'organization'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'organization_id__in'

    default_value = int(1)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_orgs = []
        allorgs = Organization.objects.all()
        allcps = Clusterpath.objects.all()
        orgset = set()
        cp_by_org = {}
        for org in allorgs:
            for cp in allcps:
                if org == cp.organization:
                    orgset.add(org)
                    cp_by_org[str(org)] = int(cp.organization.id)

        sysadds = Sysadmin.objects.all()
        current_user = request.user

        if current_user.is_superuser:
            for o in orgset:
                list_of_orgs.append(
                    (cp_by_org[str(o)], str(o))
                )
        else:
            for sa in sysadds:
                if str(sa) == str(current_user):
                    saorgs = sa.get_organizations()
                    for org in orgset:
                        for saorg in saorgs:
                            if saorg == org:
                                list_of_orgs.append(
                                    (cp_by_org[str(org)], str(org))
                                )

        #                    if self.default_value == int(1):
        #                        homeorg = sa.get_home_organization()
        #                        self.default_value = int(homeorg.id)
        # msg = "list_of_orgs for " + str(current_user) + " : " + str(list_of_orgs)
        # logger.debug(msg)
        return sorted(list_of_orgs, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """

        requestid = self.value()

        sysad = Sysadmin.objects.filter(name=request.user)
        if sysad.count() == 1:
            if int(requestid) != 1:
                self.default_value = sysad[0].organization.id
                qs = queryset.filter(organization_id=requestid)
            else:
                allorgs = sysad[0].get_organizations()
                oidlist = []
                for o in allorgs:
                    oidlist.append(int(o.id))
                qs = queryset.filter(organization_id__in=oidlist)
            return qs
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(OrganizationListFilter, self).value()
        if value is None:
            if self.default_value is None:
                first_organization = Organization.objects.first()
                value = None if first_organization is None else first_organization.id
                self.default_value = value
            else:
                value = self.default_value
        return str(value)


class HostnameListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Host name starting with'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'name'

    default_value = int(0)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_first_letters = []
        i = int(1)
        for c in char_range('a', 'z'):
            list_of_first_letters.append((str(i), str(c)))
            i = i + int(1)
        list_of_first_letters.append((str(i), str('137.75.')))
        return sorted(list_of_first_letters, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """

        requestid = self.value()
        if requestid != str(0):
            fl = ''
            i = int(1)
            for c in char_range('a', 'z'):
                if requestid == str(i):
                    fl = c
                    break
                i = i + 1
            if requestid == str(27):
                fl = '1'
            if fl != '':
                queryset = queryset.filter(name__istartswith=fl)
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(HostnameListFilter, self).value()
        if value is None:
            if self.default_value is None:
                self.default_value = 0
            else:
                value = self.default_value
        return str(value)


class NodenumberListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Node'
    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'node_id'

    default_value = int(0)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        node_id_set = set()
        list_of_nodes = []
        allslots = ClusterSlot.objects.all()
        for s in allslots:
            node_id_set.add(int(s.node_id))
        for i in range(1, int(len(node_id_set) + int(1))):
            list_of_nodes.append((str(i), str(i)))

        return sorted(list_of_nodes, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """

        requestid = self.value()
        if requestid != str(0):
            queryset = queryset.filter(node_id=requestid)
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(NodenumberListFilter, self).value()
        if value is None:
            if self.default_value is None:
                self.default_value = 0
            else:
                value = self.default_value
        return str(value)


class NodeidListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Node'
    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'nodeid'

    default_value = int(0)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        node_id_set = set()
        list_of_nodes = []
        allids = ClusterNode.objects.all()
        for c in allids:
            node_id_set.add(int(c.id))
        for i in range(1, int(len(node_id_set) + int(1))):
            list_of_nodes.append((str(i), str(i)))

        return sorted(list_of_nodes, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """

        requestid = self.value()
        if requestid != str(0):
            queryset = queryset.filter(nodeid=requestid)
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(NodeidListFilter, self).value()
        if value is None:
            if self.default_value is None:
                self.default_value = 0
            else:
                value = self.default_value
        return str(value)

class QuotaOrganizationListFilter(admin.SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'quota'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'quota_id'

    # Custom attributes
    related_filter_parameter = 'quota__organization__id__exact'

    default_value = int(1)

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_quotausages = set()
        queryset = QuotaUsage.objects.order_by('quota_id')
        if self.related_filter_parameter in request.GET:
            queryset = queryset.filter(organization_id=request.GET[self.related_filter_parameter])
        for qu in queryset:
            label = str(qu)
            label = re.sub(settings.QUMULO_BASE_PATH, "", label)
            label = re.sub("^/", "", label)
            label = re.sub("/_usage", "", label)
            list_of_quotausages.add(
                (str(qu.quota.id), label.strip().encode('ascii', 'ignore')))
        return sorted(list_of_quotausages, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value to decide how to filter the queryset.
        if self.value():
            return queryset.filter(quota_id=self.value())
        return queryset

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(QuotaOrganizationListFilter, self).value()
        if value is None:
            if self.default_value is None:
                first_quota = QuotaUsage.objects.first()
                value = None if first_quota is None else first_quota.id
                self.default_value = value
            else:
                value = int(-11)
        return str(value)


def get_sysad(request):
    sysadmin = Sysadmin.objects.filter(name=request.user)
    sysad = 'unknown'
    if sysadmin.count() == 1:
        sysad = sysadmin[0].name
    return sysad


def change_msg(self, obj, form, sysad):
    now = datetime.datetime.utcnow()
    msg = str(now) + ":" + str(sysad)
    # logger.info(msg)
    mytype = str(type(self))
    mytype = mytype.replace("provision.admin.", "")
    mytype = mytype.replace("Admin", "")
    mytype = mytype.replace("<class '", "")
    mytype = mytype.replace("'>", "")

    objname = False
    if mytype == 'NfsExport':
        objname = str(obj.exportpath)
    if mytype == 'Clusterpath':
        objname = str(obj.dirpath)
    if objname is False:
        objname = (obj.name)

    if objname is False:
        msg = "orig_mytype_is_" + str(self)
        logger.info(msg)
        msg = "objname_unknown_for_" + str(mytype)
        logger.info(msg)
        objname = (msg)

    if len(form.changed_data) > 0:
        newvals = {}
        for f in form.changed_data:
            if form.cleaned_data[f]:
                newvals[f] = form.cleaned_data[f]
        msg = msg + ":changed_" + mytype + ":" + objname + ":" + str(form.changed_data) + ":" + str(newvals)
    else:
        msg = msg + ":saved_withoutchange_" + mytype + ":" + str(objname) + ":[]:{}"
    return msg


def was_deleted(self, obj_id):
    # did deletion really occur?
    myobj = self.model.objects.filter(id=obj_id)
    try:
        name = myobj[0].name
        deleted = False
    except:
        deleted = True
    return deleted


class ActivityAdmin(admin.ModelAdmin):
    list_display = (
    'host', 'activitytype', 'sample_mean', 'sample_std', 'std_div_mean', 'numsamples', 'get_validtime', 'basefilepath')
    list_display_links = (
    'host', 'activitytype', 'sample_mean', 'sample_std', 'std_div_mean', 'numsamples', 'get_validtime', 'basefilepath')

    readonly_fields = ('host', 'activitytype', 'mean', 'std', 'numsamples', 'basefilepath')

    list_filter = (ActivityTypeListFilter, ActivityTypeHostnameListFilter)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(ActivityAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions


class ActivityFetchAdmin(admin.ModelAdmin):
    list_display = (
    'numhosts', 'numactivities', 'numsamples', 'fetch_date', 'fetch_duration', 'storage_duration', 'updated')
    list_display_links = (
    'numhosts', 'numactivities', 'numsamples', 'fetch_date', 'fetch_duration', 'storage_duration', 'updated')

    readonly_fields = (
    'numhosts', 'numactivities', 'numsamples', 'fetch_date', 'fetch_duration', 'storage_duration', 'updated')

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(ActivityFetchAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions


class ActivityStatAdmin(admin.ModelAdmin):
    list_display = (
    'host', 'activity_name', 'population_mean', 'population_std', 'numsamples', 'validfrom', 'validto', 'basefilepath')
    list_display_links = (
    'host', 'activity_name', 'population_mean', 'population_std', 'numsamples', 'validfrom', 'validto', 'basefilepath')

    readonly_fields = (
    'activitytype', 'population_mean', 'population_std', 'numsamples', 'validfrom', 'validto', 'basefilepath')

    list_filter = (ActivityTypeListFilter, ActivityTypeHostnameListFilter)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(ActivityStatAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions


class ActivityStatCompAdmin(admin.ModelAdmin):
    list_display = (
    'activity_name', 'activitytype', 'meandifference', 'stddifference', 'variancedifference', 'stdratio',
    'varianceratio', 'get_numdays', 'validfrom', 'validto')
    list_display_links = (
    'activity_name', 'activitytype', 'meandifference', 'stddifference', 'variancedifference', 'stdratio',
    'varianceratio', 'get_numdays', 'validfrom', 'validto')

    readonly_fields = (
    'activity_name', 'activitytype', 'meandifference', 'stddifference', 'variancedifference', 'stdratio',
    'varianceratio', 'get_numdays', 'validfrom', 'validto')

    list_filter = (ActivityTypeListFilter,)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(ActivityStatCompAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions


class ActivityRunningStatAdmin(admin.ModelAdmin):
    list_display = (
    'get_numdays', 'host', 'activitytype', 'population_mean', 'population_std', 'numsamples', 'validfrom', 'validto')
    list_display_links = (
    'get_numdays', 'host', 'activitytype', 'population_mean', 'population_std', 'numsamples', 'validfrom', 'validto')

    readonly_fields = (
    'get_numdays', 'host', 'activitytype', 'population_mean', 'population_std', 'numsamples', 'validfrom', 'validto')

    list_filter = (ActivityTypeListFilter, HostnameListFilter)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(ActivityRunningStatAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

class ClusterAdmin(admin.ModelAdmin):
    list_display = ('name',)
    list_display_links = ('name',)


class ClusterpathAdmin(admin.ModelAdmin):
    list_display = ('dirpath', 'do_not_delete', 'creator', 'updater')
    list_display_links = ('dirpath',)
    # list_display = ('dirpath','do_not_delete')
    # list_display_links = ('dirpath','do_not_delete')
    exclude = ('dirid', 'updater')
    list_filter = (OrganizationListFilter,)

    def save_model(self, request, obj, form, change):
        # enforce trailing '/' on dirpath
        if obj.dirpath[len(obj.dirpath) - 1:len(obj.dirpath)] != '/':
            obj.dirpath = obj.dirpath + "/"
        msg = " obj.dirpath is " + str(obj.dirpath)
        logger.info(msg)

        # now we can save the object and call super
        obj.save()
        super(ClusterpathAdmin, self).save_model(request, obj, form, change)

        # who created/update this clusterpath
        sysad = get_sysad(request)
        createdby = obj.get_creator()
        if createdby is 'unknown':
            obj.creator = sysad
        obj.updater = sysad

        msg = change_msg(self, obj, form, sysad)
        logger.info(msg)

    def delete_model(self, request, obj):
        sysad = get_sysad(request)
        obj.set_updater(sysad)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if obj.get_do_not_delete() is True:
            messages.warning(request, "Clusterpath " + str(obj.dirpath) + " is marked do not delete.")
            msg = msg + ":deletemodelClusterpath_do_not_delete:"
        else:
            msg = msg + ":delete_from_cluster:" + str(obj.dirpath) + ":" + get_sysad(request)
            logger.info(msg)
            obj.delete_from_cluster()
            super(ClusterpathAdmin, self).delete_model(request, obj)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletemodelClusterpath:"
        msg = msg + str(obj.dirpath) + ":" + get_sysad(request)
        logger.info(msg)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determines the HttpResponse for the delete_view stage.
        """

        opts = self.model._meta

        if IS_POPUP_VAR in request.POST:
            popup_response_data = json.dumps({
                'action': 'delete',
                'value': str(obj_id),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        if was_deleted(self, obj_id) is True:
            self.message_user(
                request,
                _('The %(name)s "%(obj)s" was deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('%(name)s "%(obj)s" and associated objects were not deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, post_url
            )
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.Clusterpath.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations().order_by('name')
                kwargs['queryset'] = orglist
                kwargs['initial'] = sysadmin[0].get_home_organization().id

        if str(db_field) == 'provision.Clusterpath.quota':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations()
                orgset = set()
                for org in orglist:
                    orgset.add(org)
                orglist = []
                for o in orgset:
                    orglist.append(o)
                kwargs['queryset'] = Quota.objects.filter(organization__in=orglist).order_by('name')
                qr = Quota.objects.filter(name='#None')
                if qr.count() > 0:
                    kwargs['initial'] = qr[0].id

        if str(db_field) == 'provision.Clusterpath.cluster':
            clusters = Cluster.objects.filter()
            if clusters.count() == 1:
                kwargs['initial'] = clusters[0]

        return super(ClusterpathAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(ClusterpathAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
        if str(db_field) == 'provision.Clusterpath.creator':
            now = datetime.datetime.utcnow()
            msg = str(now) + ":inClusterpathEditor:" + str(db_field) + ":" + get_sysad(request)
            logger.info(msg)
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = str(sysadmin[0])

        if str(db_field) == 'provision.Clusterpath.dirpath':
            if settings.QUMULO_BASE_PATH not in field.initial:
                sysadmin = Sysadmin.objects.filter(name=request.user)
                if sysadmin.count() == 1:
                    homeorg = sysadmin[0].get_home_organization()
                field.initial = settings.QUMULO_BASE_PATH + "/" + str(homeorg) + "/new_clusterpath"
        return field


class ClusterSlotAdmin(admin.ModelAdmin):
    list_display = ('qid', 'state', 'slot_type', 'disk_type', 'disk_model', 'capacity', 'node_id', 'slot')
    list_display_links = ('qid', 'state', 'slot_type', 'disk_type', 'disk_model', 'capacity', 'node_id', 'slot')
    list_filter = (NodenumberListFilter,)


class ConnectionAdmin(admin.ModelAdmin):
    # list_display = ('id', 'nodeid', 'connections_per_host', 'hosts_by_num_connections', 'validtime')
    # list_display_links = ('id', 'nodeid', 'connections_per_host', 'hosts_by_num_connections', 'validtime')
    list_display = ('id', 'nodeid', 'Connections_By_Host', 'Hosts_By_Connection', 'validtime')
    list_display_links = ('id', 'nodeid', 'Connections_By_Host', 'Hosts_By_Connection', 'validtime')
    readonly_fields = (
    'id', 'connectiontype', 'connections_per_host', 'hosts_by_num_connections', 'nodeid', 'Connections_By_Host',
    'Hosts_By_Connection', 'validtime')
    list_filter = (NodeidListFilter,)


class ConnectionFetchAdmin(admin.ModelAdmin):
    list_display = (
    'id', 'node_id_list', 'numhosts', 'numconnections', 'host_connections_link', 'beginfetch', 'fetch_duration',
    'storage_duration', 'updated')
    list_display_links = (
    'id', 'node_id_list', 'numhosts', 'numconnections', 'host_connections_link', 'beginfetch', 'fetch_duration',
    'storage_duration', 'updated')
    readonly_fields = (
    'id', 'connections', 'numhosts', 'numconnections', 'beginfetch', 'fetch_duration', 'storage_duration', 'updated' )


class HostAdmin(admin.ModelAdmin):
    list_display = ('name', 'ipaddr', 'ipzone', 'organization')
    list_display_links = ('name', 'ipaddr', 'ipzone', 'organization')
    list_filter = (HostnameListFilter,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.Host.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations().order_by('name')
                kwargs['queryset'] = orglist
                kwargs['initial'] = sysadmin[0].get_home_organization().id

        if str(db_field) == 'provision.Host.ipzone':
            kwargs['queryset'] = IPzone.objects.order_by('name')

        return super(HostAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

class IPzoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'ipzmarker', 'creator', 'updater')
    list_display_links = ('name',)
    list_filter = (OrganizationListFilter,)
    exclude = ('ipaddrs', 'updater', 'ipzmarker', 'initialized')
    #exclude = ('ipaddrs', 'updater', 'ipzmarker', 'initialized')

    def save_model(self, request, obj, form, change):
        # now we can save the object and call super
        obj.save()
        super(IPzoneAdmin, self).save_model(request, obj, form, change)
        obj.set_ipzone_marker()

        # who created/update this ipzone
        sysad = get_sysad(request)
        createdby = obj.get_creator()
        if str(createdby) == 'unknown':
            obj.creator = sysad
        obj.updater = sysad
        msg = change_msg(self, obj, form, sysad)
        logger.info(msg)

    def save_related(self, request, form, formsets, change):
        super(IPzoneAdmin, self).save_related(request, form, formsets, change)

        # Locate and save (update) associated NSF exports
        # collect parents as a set since theoretically a restriction could be used by more than one export
        # note: this code is necessarily repeated in restriction.save()
        myid = request.path.split('/')
        pathlen = len(myid) - 2
        if 'change' in str(request.path):
            myid = int(myid[pathlen - 1])
        else:
            if 'add' not in str(request.path):
                myid = int(myid[pathlen])
            else:
                now = datetime.datetime.utcnow()
                msg = str(now) + ":save_related_Ipzone_unrecognized path:" + str(request.path) + ":" + get_sysad(
                    request)
                logger.info(msg)
                return

        #   Locate and save (update) associated NFS Restrictions and then NFS Exports, but only if immutable flag is False (the default -- so that GUI created objects are deleted)
        qs = IPzone.objects.filter(id=myid)
        if qs.count() == 1:
                if qs[0].is_immutable() is False:
                    rpset = set()
                    for r in Restriction.objects.all():
                        ipzones = r.get_ipzones()
                        for z in ipzones:
                            if myid == z.id:
                                rpset.add(r)
                    for r in rpset:
                        r.save()

                    nsfxparents = set()
                    for x in NfsExport.objects.all():
                        xrqs = x.restrictions.get_queryset()
                        for xr in xrqs:
                            for r in rpset:
                                if r == xr:
                                    nsfxparents.add(x)
                    for x in nsfxparents:
                        #    msg = "   saving restriction " + str(r)
                        #    logger.debug(msg)
                        x.save(update_on_cluster=True)


    def response_change(self, request, obj):
        """
        Determines the HttpResponse for the change_view stage.
        """

        if IS_POPUP_VAR in request.POST:
            opts = obj._meta
            to_field = request.POST.get(TO_FIELD_VAR)
            attr = str(to_field) if to_field else opts.pk.attname
            # Retrieve the `object_id` from the resolved pattern arguments.
            value = request.resolver_match.args[0]
            new_value = obj.serializable_value(attr)
            popup_response_data = json.dumps({
                'action': 'change',
                'value': six.text_type(value),
                'obj': six.text_type(obj),
                'new_value': six.text_type(new_value),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        opts = self.model._meta
        pk_value = obj._get_pk_val()
        preserved_filters = self.get_preserved_filters(request)

        is_immutable = obj.is_immutable()

        msg_dict = {
            'name': force_text(opts.verbose_name),
            'obj': format_html('<a href="{}">{}</a>', urlquote(request.path), obj),
        }
        if "_continue" in request.POST:
            if is_immutable is True:
                msg = format_html(
                    _('The {name} "{obj}" is immutable and was not changed. You may edit it again below.'),
                    **msg_dict
                )
            else:
                msg = format_html(
                    _('The {name} "{obj}" was changed successfully. You may edit it again below.'),
                    **msg_dict
                )
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = request.path
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        elif "_saveasnew" in request.POST:
            if is_immutable is True:
                msg = format_html(
                    _('The {name} "{obj}" is immutable and was not changed. You may edit it again below.'),
                    **msg_dict
                )
            else:
                msg = format_html(
                    _('The {name} "{obj}" was added successfully. You may edit it again below.'),
                    **msg_dict
                )
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = reverse('admin:%s_%s_change' %
                                   (opts.app_label, opts.model_name),
                                   args=(pk_value,),
                                   current_app=self.admin_site.name)
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        elif "_addanother" in request.POST:
            if is_immutable is True:
                msg = format_html(
                    _('The {name} "{obj}" is immutable and was not changed. You may add another {name} below.'),
                    **msg_dict
                )
            else:
                msg = format_html(
                    _('The {name} "{obj}" was changed successfully. You may add another {name} below.'),
                    **msg_dict
                )
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = reverse('admin:%s_%s_add' %
                                   (opts.app_label, opts.model_name),
                                   current_app=self.admin_site.name)
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        else:
            if is_immutable is True:
                msg = format_html(
                    _('The {name} "{obj}" is immutable and was not changed.'),
                    **msg_dict
                )
            else:
                msg = format_html(
                    _('The {name} "{obj}" was changed successfully.'),
                    **msg_dict
                )
            self.message_user(request, msg, messages.SUCCESS)
            return self.response_post_save_change(request, obj)

    def delete_model(self, request, obj):
        sysad = get_sysad(request)
        obj.set_updater(sysad)
        now = datetime.datetime.utcnow()
        msg = str(now) + ":delete_model_Ipzone:" + str(obj.name) + ":" + get_sysad(request)
        logger.info(msg)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if obj.is_immutable() is True:
            messages.warning(request, "IPzone " + str(obj.name) + " is immutable")
            msg = msg + ":deletemodelIpzone_is_immutable:"
        else:
            msg = "delete_from_cluster" + str(obj.name) + ":" + get_sysad(request)
            logger.info(msg)
            obj.delete_from_cluster()
            super(IPzoneAdmin, self).delete_model(request, obj)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletedIpzone:"
        msg = msg + str(obj.name) + ":" + get_sysad(request)
        logger.info(msg)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determines the HttpResponse for the delete_view stage.
        """

        opts = self.model._meta

        if IS_POPUP_VAR in request.POST:
            popup_response_data = json.dumps({
                'action': 'delete',
                'value': str(obj_id),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        if was_deleted(self, obj_id) is True:
            self.message_user(
                request,
                _('The %(name)s "%(obj)s" was deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('%(name)s "%(obj)s" and associated objects were not deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, post_url
            )
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.IPzone.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations()
                kwargs['queryset'] = orglist
                kwargs['initial'] = sysadmin[0].get_home_organization().id
            return super(IPzoneAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(IPzoneAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
        if str(db_field) == 'provision.IPzone.creator':
            now = datetime.datetime.utcnow()
            msg = str(now) + ":inIPzoneEditor:" + str(db_field) + ":" + get_sysad(request)
            logger.info(msg)
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = str(sysadmin[0])
        return field


class NfsExportAdmin(admin.ModelAdmin):
    list_display = ('clusterpath', 'exportpath', 'description', 'creator', 'updater', 'organization', 'do_not_delete')
    list_display_links = ('clusterpath', 'exportpath', 'description', 'organization')
    # list_display = ('clusterpath', 'exportpath', 'description', 'do_not_delete')
    # list_display_links = ('clusterpath', 'exportpath', 'description', 'do_not_delete')
    list_filter = (OrganizationListFilter,)
    exclude = ('exportid', 'organization', 'updater')

    # form = NfsExportAdminForm

    def save_model(self, request, obj, form, change):
        # Must save an export before its restrictions can be saved -- cannot due this is the save()
        # method since the form data gets cleared when the object is created (with no restrictions)
        super(NfsExportAdmin, self).save_model(request, obj, form, change)
        restrictions = form.cleaned_data['restrictions']
        for r in restrictions:
            obj.restrictions.add(r)

        # now we can save the object and call super
        obj.save()
        super(NfsExportAdmin, self).save_model(request, obj, form, change)

        # who created/update this export -- must do this after super to preserve creator
        sysad = get_sysad(request)
        createdby = obj.get_creator()
        if str(createdby) == 'unknown':
            obj.creator = sysad
        obj.updater = sysad

        msg = change_msg(self, obj, form, sysad)
        logger.info(msg)

    def delete_model(self, request, obj):
        sysad = get_sysad(request)
        # obj.set_updater(sysad)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if obj.get_do_not_delete() is True:
            messages.warning(request, "NFSExport " + str(obj.exportpath) + " is marked do no delete.")
            msg = msg + ":do_not_delete_NfsExport:"
            logger.info(msg)
        else:
            msg = msg + ":delete_from_cluster:" + str(obj.exportpath) + ":" + str(sysad)
            logger.info(msg)
            obj.delete_from_cluster()
            super(NfsExportAdmin, self).delete_model(request, obj)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletedNFSExport:"
        msg = msg + str(obj.exportpath) + ":" + str(sysad)
        logger.info(msg)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determines the HttpResponse for the delete_view stage.
        """

        opts = self.model._meta

        if IS_POPUP_VAR in request.POST:
            popup_response_data = json.dumps({
                'action': 'delete',
                'value': str(obj_id),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        if was_deleted(self, obj_id) is True:
            self.message_user(
                request,
                _('The %(name)s "%(obj)s" was deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('%(name)s "%(obj)s" and associated objects were not deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, post_url
            )
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.NfsExport.clusterpath':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                orglist = sysadmin[0].get_organizations()
                orgset = set()
                for org in orglist:
                    orgset.add(org)
                orglist = []
                for o in orgset:
                    orglist.append(o)
                if len(orglist) > 0:
                    orglist.sort()
                kwargs['queryset'] = Clusterpath.objects.filter(organization__in=orglist).order_by('dirpath')
                homeorg = sysadmin[0].get_home_organization()
                kwargs['initial'] = Clusterpath.objects.filter(organization=homeorg).order_by('dirpath')[0]

        if str(db_field) == 'provision.NfsExport.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations().order_by('name')
                kwargs['queryset'] = orglist

        return super(NfsExportAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.NfsExport.restrictions':
            kwargs['queryset'] = Restriction.objects.all().order_by('name')
        return super(NfsExportAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(NfsExportAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
        if str(db_field) == 'provision.NfsExport.exportpath':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = "/" + str(sysadmin[0].get_home_organization()) + "/"

        if str(db_field) == 'provision.NfsExport.creator':
            now = datetime.datetime.utcnow()
            msg = str(now) + ":inNfsExportEditor:" + str(db_field) + ":" + get_sysad(request)
            logger.info(msg)
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = str(sysadmin[0])
        return field


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name',)
    list_display_links = ('name',)

class QuotaAdmin(admin.ModelAdmin):
    list_display = (
        'percentage_used', 'name', 'current_size', 'current_usage', 'organization', 'nextwarn', 'nextcritical',
        'primary', 'secondary',
    )
    list_display_links = (
        'percentage_used', 'name', 'current_size', 'current_usage', 'organization', 'nextwarn', 'nextcritical',
        'primary', 'secondary')
    # sort in descending order
    ordering = ('-pctusage',)
    # list_display = ('name', 'current_size', 'current_usage', 'percentage_used', 'do_not_delete')
    # list_display_links = ('name', 'current_size', 'current_usage', 'percentage_used', 'do_not_delete')
    list_filter = (OrganizationListFilter,)
    exclude = (
    'qid', 'usage', 'pctusage', 'lastwarn', 'lastcritical', 'lastfull', 'colorname', 'updater', 'updated_on_cluster')

    # exclude = ('qid', 'usage', 'pctusage', 'colorname', 'creator')

    def save_model(self, request, obj, form, change):
        # enforce trailing '/' on name
        if obj.name[len(obj.name) - 1:len(obj.name)] != '/':
            obj.name = obj.name + "/"
        msg = " obj.name is " + str(obj.name)
        logger.info(msg)

        # now we can save the object and call super
        obj.save()
        super(QuotaAdmin, self).save_model(request, obj, form, change)

        # who created/update this quota -- must do this after super to preserve creator
        sysad = get_sysad(request)
        createdby = obj.get_creator()
        if str(createdby) == 'unknown':
            obj.creator = sysad
        obj.updater = sysad

        msg = change_msg(self, obj, form, sysad)
        logger.info(msg)

        # if size or units were changed, recompute the use percentage
        updated = False
        if "size" in str(form.changed_data) or "units" in str(form.changed_data):

            #  cannot call obj.set_pctusage() here -- its calls save() -- so duplicate code is necessary
            size = float(obj.get_size())
            units = str(obj.get_units())
            size_times_units = obj.get_size_times_units(size, units)
            if size_times_units != 0.0:
                obj.pctusage = float(obj.get_usage()) / float(size_times_units)
            else:
                obj.pctusage = -1.0

            # clear all email trottle fields
            obj.lastwarn = 0
            obj.lastcritical = 0
            obj.lastfull = 0
            updated = True

        if "warnfreq" in str(form.changed_data) or "criticalfreq" in str(form.changed_data) or "fullfreq" in str(
                form.changed_data):
            # update email message 'last*' fields since the user may have changed them
            now = datetime.datetime.utcnow()
            nowutc = int(now.strftime('%s'))
            obj.lastwarn = nowutc + obj.get_warn_delay()
            obj.lastcritial = nowutc + obj.get_critical_delay()
            obj.lastfull = nowutc + obj.get_full_delay()
            updated = True

        # check usage if anything was changed
        try:
            test = form.changed_data.keys()
            msg = ":quota save_model:" + str(obj.name) + ":" + str(obj.id) + ":form.changed_data" + str(
                form.changed_data)
            logger.info(msg)
            obj.check_usage()
        except:
            msg = ":quota save_model:" + str(obj.name) + ":" + str(obj.id) + ":no keys for form.changed_data = " + str(
                form.changed_data)
            logger.info(msg)

        if updated is True:
            super(QuotaAdmin, self).save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        sysad = get_sysad(request)
        obj.set_updater(sysad)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if obj.get_do_not_delete() is True:
            messages.warning(request, "Quota " + str(obj.name) + " is marked do not delete.")
            msg = msg + ":deletemodelQuota_do_not_delete:"
        else:
            msg = msg + ":delete_from_cluster:" + str(obj.name) + ":" + get_sysad(request)
            logger.info(msg)
            obj.delete_from_cluster()
            super(QuotaAdmin, self).delete_model(request, obj)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletemodelQuota:"
        msg = msg + str(obj.name) + ":" + get_sysad(request)
        logger.info(msg)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determines the HttpResponse for the delete_view stage.
        """

        opts = self.model._meta

        if IS_POPUP_VAR in request.POST:
            popup_response_data = json.dumps({
                'action': 'delete',
                'value': str(obj_id),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        if was_deleted(self, obj_id) is True:
            self.message_user(
                request,
                _('The %(name)s "%(obj)s" was deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('%(name)s "%(obj)s" and associated objects were not deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, post_url
            )
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.Quota.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations()
                orgset = set()
                for org in orglist:
                    orgset.add(org)
                orglist = []
                for o in orgset:
                    orglist.append(o)
                if len(orglist) > 0:
                    orglist.sort()
                kwargs['queryset'] = Organization.objects.filter(name__in=orglist).order_by('name')
                kwargs['initial'] = sysadmin[0].get_home_organization().id
        return super(QuotaAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(QuotaAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)

        if str(db_field) == 'provision.Quota.name':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = settings.QUMULO_BASE_PATH + "/" + str(
                    sysadmin[0].get_home_organization()) + "/new_quota"

        if str(db_field) == 'provision.Quota.size':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            psize = settings.DEFAULT_CLUSTER_QUOTA_LIMIT
            if sysadmin.count() > 0:
                homeorg = str(sysadmin[0].get_home_organization())
                cpname = settings.QUMULO_BASE_PATH + "/" + str(homeorg) + "/"
                qr = Clusterpath.objects.filter(dirpath=cpname)
                if qr.count() > 0:
                    qr = qr[0]
                    psize = qr.quota.get_size()
                else:
                    try:
                        psize = settings.ORGANIZATION_QUOTA_LIMITS[homeorg]
                    except:
                        psize = settings.DEFAULT_CLUSTER_QUOTA_LIMIT
            field.initial = int(
                math.floor((float(psize) * float(100 - settings.QUOTA_SAFETY_MARGIN_PERCENTAGE) / 100.0)))

        if str(db_field) == 'provision.Quota.creator':
            now = datetime.datetime.utcnow()
            msg = str(now) + ":inQuotaEditor:" + str(db_field) + ":" + get_sysad(request)
            logger.info(msg)
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = str(sysadmin[0])
        return field


class QuotaUsageAdmin(admin.ModelAdmin):
    list_filter = ('quota__organization', QuotaOrganizationListFilter)
    list_display = ('usage', 'quota', 'organization', 'updated',)

class QuotaEventAdmin(admin.ModelAdmin):
    list_display = ('quotaname', 'eventtype', 'percentage_used', 'mailsent_utc', 'seconds_to_next_email')
    list_display_links = ('quotaname', 'eventtype', 'percentage_used', 'mailsent_utc', 'seconds_to_next_email')


class ReportAdmin(admin.ModelAdmin):
    list_filter = (OrganizationListFilter,)
    exclude = ('organization', 'updater')

    def save_model(self, request, obj, form, change):
        # who created/update this report
        sysad = get_sysad(request)
        createdby = obj.get_creator()
        if str(createdby) == 'unknown':
            obj.creator = sysad
        obj.updater = sysad

        # now we can save the object and call super
        obj.save()
        super(ReportAdmin, self).save_model(request, obj, form, change)
        msg = change_msg(self, obj, form, sysad)
        logger.info(msg)

    def delete_model(self, request, obj):
        sysad = get_sysad(request)
        obj.set_updater(sysad)
        now = datetime.datetime.utcnow()
        msg = str(now) + ":deletemodelReport:" + str(obj.name) + ":" + get_sysad(request)
        logger.info(msg)
        super(ReportAdmin, self).delete_model(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determines the HttpResponse for the delete_view stage.
        """

        opts = self.model._meta

        if IS_POPUP_VAR in request.POST:
            popup_response_data = json.dumps({
                'action': 'delete',
                'value': str(obj_id),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        if was_deleted(self, obj_id) is True:
            self.message_user(
                request,
                _('The %(name)s "%(obj)s" was deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('%(name)s "%(obj)s" and associated objects were not deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, post_url
            )
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.Report.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations().order_by('name')
                kwargs['queryset'] = orglist

        return super(ReportAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(ReportAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
        if str(db_field) == 'provision.Report.creator':
            now = datetime.datetime.utcnow()
            msg = str(now) + ":inReportEditor:" + str(db_field) + ":" + get_sysad(request)
            logger.info(msg)
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = str(sysadmin[0])
        return field


class RestrictionAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'do_not_delete', 'creator', 'updater')
    list_display_links = ('name', 'organization')
    # list_display = ('name','do_not_delete')
    # list_display_links = ('name','do_not_delete')
    list_filter = (OrganizationListFilter,)
    exclude = ('updater',)

    def save_model(self, request, obj, form, change):
        # Must save a Restriction before its Ipzones can be saved -- cannot due this is the save()
        # method since the form data gets cleared when the object is created (with no ipzones)
        super(RestrictionAdmin, self).save_model(request, obj, form, change)
        ipzones = form.cleaned_data['ipzones']
        msg = "   ipzones: " + str(ipzones)
        # logger.debug(msg)
        for z in ipzones:
            obj.ipzones.add(z)

        # now we can save the object and then call super
        obj.save()
        super(RestrictionAdmin, self).save_model(request, obj, form, change)

        # who created/update this restriction
        sysad = get_sysad(request)
        createdby = obj.get_creator()
        if str(createdby) == 'unknown':
            obj.creator = sysad
        obj.updater = sysad

        msg = change_msg(self, obj, form, sysad)
        logger.info(msg)

    def save_related(self, request, form, formsets, change):
        super(RestrictionAdmin, self).save_related(request, form, formsets, change)

        # Locate and save (update) associated NSF exports
        # collect parents as a set since theoretically a restriction could be used by more than one export
        # note: this code is necessarily repeated in restriction.save()
        myid = request.path.split('/')
        pathlen = len(myid) - 2
        if 'change' in str(request.path):
            myid = int(myid[pathlen - 1])
        else:
            if 'add' not in str(request.path):
                myid = int(myid[pathlen])
            else:
                now = datetime.datetime.utcnow()
                msg = str(now) + ":save_related_Restriction_unrecognized path:" + str(request.path) + ":" + get_sysad(
                    request)
                logger.info(msg)
                return

        nsfparents = set()
        for x in NfsExport.objects.all():
            xrqs = x.get_restrictions()
            for xr in xrqs:
                if xr.id == myid:
                    nsfparents.add(x)

        for x in nsfparents:
            msg = "   save_related nfsexport " + str(x) + " for restriction " + str(myid)
            logger.info(msg)
            qs = NfsExport.objects.filter(id=x.id)
            if qs.count() == 1:
                qs[0].save(update_on_cluster=True)


    def delete_model(self, request, obj):
        sysad = get_sysad(request)
        obj.set_updater(sysad)
        now = datetime.datetime.utcnow()
        msg = str(now)
        if obj.get_do_not_delete() is True:
            messages.warning(request, "Restriction " + str(obj.name) + " is marked do not delete.")
            msg = msg + ":deletemodelRestriction_do_not_delete:"
        else:
            msg = msg + ":delete_from_cluster:" + str(obj.name) + ":" + get_sysad(request)
            logger.info(msg)
            obj.delete_from_cluster()
            super(RestrictionAdmin, self).delete_model(request, obj)
            now = datetime.datetime.utcnow()
            msg = str(now) + ":deletemodelRestriction:"
        msg = msg + str(obj.name) + ":" + get_sysad(request)
        logger.info(msg)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determines the HttpResponse for the delete_view stage.
        """

        opts = self.model._meta

        if IS_POPUP_VAR in request.POST:
            popup_response_data = json.dumps({
                'action': 'delete',
                'value': str(obj_id),
            })
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/popup_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/popup_response.html' % opts.app_label,
                'admin/popup_response.html',
            ], {
                                        'popup_response_data': popup_response_data,
                                    })

        if was_deleted(self, obj_id) is True:
            self.message_user(
                request,
                _('The %(name)s "%(obj)s" was deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('%(name)s "%(obj)s" and associated objects were not deleted.') % {
                    'name': force_text(opts.verbose_name),
                    'obj': force_text(obj_display),
                },
                messages.SUCCESS,
            )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, post_url
            )
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.Restriction.ipzones':
            #kwargs['queryset'] = IPzone.objects.all().order_by('name').exclude(name=settings.NONE_NAME)
            kwargs['queryset'] = IPzone.objects.all().order_by('name')
            form = super(RestrictionAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

        if str(db_field) == 'provision.Restriction.individual_hosts':
            kwargs['queryset'] = Host.objects.all().order_by('name')
            form = super(RestrictionAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)
            nhost = Host.objects.filter(name='#None')
            if nhost.count() > 0:
                dict = {}
                dict[nhost[0].id] = True
                form.initial = dict
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if str(db_field) == 'provision.Restriction.organization':
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() == 1:
                orglist = sysadmin[0].get_organizations().order_by('name')
                kwargs['queryset'] = orglist
                kwargs['initial'] = sysadmin[0].get_home_organization().id
        return super(RestrictionAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(RestrictionAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
        if str(db_field) == 'provision.Restriction.creator':
            now = datetime.datetime.utcnow()
            msg = str(now) + ":inRestrictionEditor:" + str(db_field) + ":" + get_sysad(request)
            logger.info(msg)
            sysadmin = Sysadmin.objects.filter(name=request.user)
            if sysadmin.count() > 0:
                field.initial = str(sysadmin[0])
        return field


class SysadminAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization')
    list_display_links = ('name', 'organization')


class WinDCAdmin(admin.ModelAdmin):
    list_display = ('name',)
    list_display_links = ('name',)


# http://djangoweekly.com/blog/post/viewbrowse-all-django-admin-edits-recent-actions-listing
class LogEntryAdmin(admin.ModelAdmin):
    readonly_fields = ('content_type',
                       'user',
                       'action_time',
                       'object_id',
                       'object_repr',
                       'action_flag',
                       'change_message'
                       )

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(LogEntryAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

admin.site.register(Cluster, ClusterAdmin)
admin.site.register(Clusterpath, ClusterpathAdmin)
admin.site.register(DNSdomain)
admin.site.register(Host, HostAdmin)
admin.site.register(IPzone, IPzoneAdmin)
admin.site.register(NfsExport, NfsExportAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Quota, QuotaAdmin)
admin.site.register(QuotaEvent, QuotaEventAdmin)
admin.site.register(QuotaUsage, QuotaUsageAdmin)
admin.site.register(Report, ReportAdmin)
admin.site.register(Restriction, RestrictionAdmin)
admin.site.register(Sysadmin, SysadminAdmin)
admin.site.register(WinDC, WinDCAdmin)
admin.site.register(LogEntry, LogEntryAdmin)
admin.site.register(ClusterSlot, ClusterSlotAdmin)
admin.site.register(Activity, ActivityAdmin)
admin.site.register(ActivityStat, ActivityStatAdmin)
admin.site.register(ActivityRunningStat, ActivityRunningStatAdmin)
admin.site.register(ActivityFetch, ActivityFetchAdmin)
admin.site.register(ActivityStatComp, ActivityStatCompAdmin)
admin.site.register(Connection, ConnectionAdmin)
admin.site.register(ConnectionType)
admin.site.register(ConnectionFetch, ConnectionFetchAdmin)
#admin.site.register(UserSession)

"""qrba URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.contrib import admin
from provision import views

urlpatterns = [
    url(r'^admin/provision/host/nodnshosts/$', views.no_dns_hosts, name='nodnshosts'),
    url(r'^admin/provision/nfsexport/(?P<xid>[0-9]+)/metadata/$', views.metadata, name='metadata'),
    url(r'^admin/provision/ipzone/(?P<ipzm>[0-9]+.[0-9]+.[0-9]+.[0-9]+)/ipzone_from_ipzm/$', views.ipzone_from_ipzm, name='ipzone_from_ipzm'),
    url(r'^admin/provision/nfsexport/fbcp/$', views.nfx_cplimit, name='fbcp'),
    url(r'^admin/provision/nfsexport/notadd/$', views.NFSExportDetailView.as_view(), name='index'),
    url(r'^provision/', include('provision.urls')),
    url(r'^admin/', admin.site.urls),
]

"""
A set of request processors that return dictionaries to be merged into a
template context. Each function takes the request object as its only parameter
and returns a dictionary to add to the context.

These are referenced from the 'context_processors' option of the configuration
of a DjangoTemplates backend and used by RequestContext.
"""

from __future__ import unicode_literals
import os
from qrba import settings


# http://www.aptivate.org/en/blog/2013/01/22/making-it-obvious-which-copy-of-a-django-site-you-are-using/
def deploy_env(request):
    """
    Add the deploy environment so we can show it when useful
    """
    if hasattr(settings, 'DEPLOY_ENV'):
        deploy_env = settings.DEPLOY_ENV
    else:
        local_settings_file = os.path.join(os.path.dirname(__file__), os.pardir, 'settings.py')
        if os.path.exists(local_settings_file):
            deploy_env = os.readlink(local_settings_file).split('.')[-1]
        else:
            deploy_env = "Unknown deploy environment"
    extra_context = {'deploy_env': deploy_env}
    if hasattr(settings, 'DEPLOY_ENV'):
        extra_context['deploy_env_color'] = settings.DEPLOY_ENV_COLOR
    return extra_context

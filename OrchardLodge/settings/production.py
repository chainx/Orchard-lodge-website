import os
import pathlib
import json

from OrchardLodge.settings.base import *

MEDIA_ROOT = pathlib.Path('/media/chainx/seagate/Orchard Lodge accounting data')
MEDIA_URL = '/Invoices/'
SECRET_MEDIA_ROOT = pathlib.Path('/media/chainx/seagate/Orchard lodge accounting data (PRIVATE)')

MEDIA_INVOICES = Path(os.path.join(MEDIA_ROOT, 'Invoices'))
MEDIA_REMITTANCE = Path(os.path.join(MEDIA_ROOT, 'Remittance advice'))
MEDIA_PAYMENTS = Path(os.path.join(MEDIA_ROOT, 'Bank statements'))

secret_settings = json.load(open(MEDIA_ROOT / 'Production_settings.json'))

ALLOWED_HOSTS = secret_settings['ALLOWED_HOSTS']

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = secret_settings['SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': MEDIA_ROOT / 'db.sqlite3',
    }
}
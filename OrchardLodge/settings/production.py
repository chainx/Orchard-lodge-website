import os
import pathlib
import json

from OrchardLodge.settings.base import *

linux_or_windows = 'windows' if os.name=='nt' else 'linux'
if linux_or_windows == 'linux':
    ROOT =  pathlib.Path('/media/chainx/seagate/')
elif linux_or_windows =='windows':
    ROOT = pathlib.Path('D:/')
else:
    raise ValueError(f'Unexpected operating system {os.name}')

MEDIA_ROOT = ROOT / 'Orchard Lodge accounting data'
SECRET_MEDIA_ROOT = ROOT / 'Orchard lodge accounting data (PRIVATE)'

MEDIA_URL = '/Invoices/'

MEDIA_INVOICES = MEDIA_ROOT / 'Invoices'
MEDIA_REMITTANCE = MEDIA_ROOT / 'Remittance advice'
MEDIA_PAYMENTS = MEDIA_ROOT / 'Bank statements'

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
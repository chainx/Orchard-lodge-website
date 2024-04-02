import os
import pathlib

from OrchardLodge.settings.base import *

MEDIA_ROOT = pathlib.Path(os.path.join(BASE_DIR, 'Dev data'))
MEDIA_URL = '/Invoices/'

MEDIA_INVOICES = Path(os.path.join(MEDIA_ROOT, 'Invoices'))
MEDIA_REMITTANCE = Path(os.path.join(MEDIA_ROOT, 'Remittance advice'))
MEDIA_PAYMENTS = Path(os.path.join(MEDIA_ROOT, 'Bank statements'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-o2sbv$^2%$5g%f4)3cgt+a(obft4$o&3)qt)!ynujpsmlub619'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': MEDIA_ROOT / 'db.sqlite3',
    }
}
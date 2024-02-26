from backend.invoices import get_invoice_data_from_sefton_csv

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OrchardLodge.settings.development')
import django
django.setup()

def test_get_invoice_data_from_sefton_csv():
    pass
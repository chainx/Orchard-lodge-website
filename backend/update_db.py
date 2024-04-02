import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OrchardLodge.settings.production')
import django
django.setup()

from main.models import resident
from main.models import invoice
from main.models import payment

from backend.payments import match_payments_to_resident

def add_year_and_batch_no_to_invoice_table():
    for inv in invoice.objects.all():
        inv.batch_number = str(inv.filename).split('/')[2][0]
        inv.year = str(inv.filename).split('/')[1]
        inv.save()

def use_existing_payment_filters():
    for res in resident.objects.all():
        res_filters = res.filters.split(';') if res.filters else []
        for res_filter in res_filters:
            match_payments_to_resident(res.id, res_filter)

if __name__=='__main__':
    # add_year_and_batch_no_to_invoice_table()
    # use_existing_payment_filters()
    invoice.objects.filter()
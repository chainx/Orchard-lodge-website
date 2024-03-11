import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OrchardLodge.settings.production')
import django
django.setup()

from main.models import invoice

def add_year_and_batch_no_to_invoice_table():
    invoices = invoice.objects.all()
    for inv in invoices:
        inv.batch_number = str(inv.filename).split('/')[2][0]
        inv.year = str(inv.filename).split('/')[1]
        inv.save()

if __name__=='__main__':
    add_year_and_batch_no_to_invoice_table()
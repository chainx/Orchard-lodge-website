import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import shutil

import django
django.setup()
from django.conf import settings

# Used in functions below and in views.py for the download page to order the filenames 
def file_num(filename):
        filename = os.path.basename(filename)
        if '.PDF' in filename:
             return -1 # Don't want pandas trying to read PDF when writing invoices
        if filename[1].isdigit():
            return int(filename[0:2])
        return int(filename[0])

# Used in views.py for the home page to check whether the invoices have already been written for the latest remittance advice
def latest_filenum(path):
    latest_year = max([year for year in os.listdir(path) if len(year)==4])
    dir = os.path.join(path, latest_year)
    return max([file_num(file) for file in os.listdir(dir)])

# Used in views.py, send_emails.py and invoices.py
def latest_filename(path):
    latest_year = max([year for year in os.listdir(path) if len(year)==4])
    dir = os.path.join(path, latest_year)
    return os.path.join(dir, max(os.listdir(dir), key=file_num))

def gather_sefton_remittance_advice(from_year='2013'):
    remittance_advice_files = []
    years = [year for year in sorted(os.listdir(settings.MEDIA_REMITTANCE)) if year >= from_year]
    for year in years:
        dir = settings.MEDIA_REMITTANCE / year
        filenames = sorted(os.listdir(dir), key=file_num)
        remittance_advice_files += [os.path.join(dir, filename) for filename in filenames if '.csv' in filename]
    return remittance_advice_files

def gather_all_invoices_for_resident(first_name, last_name):
    destination_path = settings.MEDIA_INVOICES / f'{first_name}_{last_name}'
    os.mkdir(destination_path)
    for year in sorted([year for year in os.listdir(settings.MEDIA_INVOICES) if len(year)==4]):
        invoice_batches = sorted(os.listdir(settings.MEDIA_INVOICES/ year), key=file_num)
        for invoice_batch in invoice_batches:
            if '.zip' not in invoice_batch and 'OBSOLETE' not in invoice_batch:
                file_path = os.path.join(settings.MEDIA_INVOICES, year, invoice_batch)
                files_to_copy = [file for file in os.listdir(file_path) if first_name in file and last_name in file]
                for file in files_to_copy:
                    shutil.copyfile(os.path.join(file_path, file), os.path.join(destination_path, file))

# if __name__=='__main__':
#     gather_all_invoices_for_resident(first_name, last_name)
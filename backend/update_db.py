import re
import pandas as pd
from random import randint
from datetime import datetime, date

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import django
django.setup()
from django.conf import settings

from main.models import resident, invoice, payment

from backend.payments import match_payments_to_resident
from backend.invoices import read_and_format_sefton_csv, get_or_add_resident

def add_customer_reference_numbers(ref_no_length):
    for res in resident.objects.filter(customer_ref_no=''):
        while True:
            customer_ref_no = ''.join([str(randint(0, 9)) for n in range(ref_no_length)])
            if not resident.objects.filter(customer_ref_no=customer_ref_no):
                break # Keep generating customer reference numbers until a unique one is generated
        res.customer_ref_no = customer_ref_no
        res.save()

def add_year_and_batch_no_to_invoice_table():
    for inv in invoice.objects.all():
        inv.batch_number = str(inv.filename).split('/')[2].split('.')[0]
        inv.year = str(inv.filename).split('/')[1]
        inv.save()

def merge_residents(id_old, id_new):
    invoice.objects.filter(Resident_id=id_old).update(Resident_id=id_new)
    payment.objects.filter(Resident_id=id_old).update(Resident_id=id_new)

def update_client_info_from_sefton_csv(client_info, year, filename):
    filename = os.path.join(settings.MEDIA_REMITTANCE, year, filename)
    df, payment_period = read_and_format_sefton_csv(filename)

    clients = df[['FormattedName', 'Sefton ID']].drop_duplicates()
    clients['Start Date'] = datetime.strptime(payment_period.split(' to ')[0], '%d/%m/%Y').date()
    clients['Leave Date'] = datetime.strptime(payment_period.split(' to ')[1], '%d/%m/%Y').date()
    
    client_info = pd.concat([client_info, clients]) if not client_info.empty else clients.copy()
    
    return client_info

def add_ID_and_start_and_leave_dates():
    client_info = pd.DataFrame()
    for year in sorted(os.listdir(settings.MEDIA_REMITTANCE)):
        filenames = sorted(os.listdir(os.path.join(settings.MEDIA_REMITTANCE, year)), key=lambda x: int(x.split('.')[0]))
        for filename in filenames:
            if '.csv' in filename:
                client_info = update_client_info_from_sefton_csv(client_info, year, filename)

    client_info = client_info.groupby(['FormattedName', 'Sefton ID']).agg({'Start Date': 'min', 'Leave Date': 'max'}).reset_index()

    # Remove duplicate names and keep the name with the latest leave date
    agg_df = client_info.groupby('Sefton ID')['FormattedName'].count().reset_index()
    duplicate_ids = agg_df[agg_df['FormattedName']>1]['Sefton ID']
    if not duplicate_ids.empty:
        print(client_info[client_info['Sefton ID'].isin(duplicate_ids)], '\n\n')
        client_info = client_info.groupby('Sefton ID').agg({'FormattedName': 'last', 'Start Date': 'min', 'Leave Date': 'max'}).reset_index()
    
    client_info.sort_values('Leave Date', inplace=True, ascending=False)
    earliest_date, latest_date = min(client_info['Start Date']), max(client_info['Leave Date'])
    
    for row in client_info.iterrows():
        res_name, sefton_id = row[1].iloc[1], row[1].iloc[0]
        res = get_or_add_resident(res_name, sefton_id, update_private_current_status=False, save=False)

        res.sefton_id = sefton_id
        if (start_date := row[1].iloc[2]) != earliest_date:
            res.start_date = start_date
        if (leave_date := row[1].iloc[3]) != latest_date:
            res.leave_date = leave_date
        
        res.save()

if __name__=='__main__':
    # add_year_and_batch_no_to_invoice_table()
    # use_existing_payment_filters()
    # merge_residents(61, 96)
    # add_customer_reference_numbers(6)
    add_ID_and_start_and_leave_dates()
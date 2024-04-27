import pandas as pd
from random import randint
from datetime import datetime, date

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OrchardLodge.settings.production')
import django
django.setup()
from django.conf import settings

from main.models import resident, invoice, payment
from django.db.models import Q

from backend.payments import match_payments_to_resident

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
    try:
        df = pd.read_csv(filename)
    except:
        df = pd.read_csv(filename, encoding='ISO-8859-1')
    
    df = df.fillna('')# if ServiceTotalLabel != 'Total for Orchard Lodge Care Home' then it may contain a note from Sefton
    df = df[df['ClientName']!='Payments not allocated to a client']
    
    payment_period = df.iloc[0]['ReportContext'].split('Payment Period from ')[1]
    end_date = datetime.strptime(payment_period.split(' to ')[1], '%d/%m/%Y').date()

    clients = df[['ClientName', 'Person']].drop_duplicates()
    clients['Name'] = clients.apply(
        lambda row: row['Person'].split()[0] + ',' + ', '.join(row['ClientName'].split(' (')[0].split(',')[::-1]),
        axis=1
    )
    clients['ID'] = clients['ClientName'].apply(lambda x: x.split(' (')[1][:-1])
    clients['Leave Date'] = end_date
    clients.drop('ClientName', axis='columns', inplace=True)
    
    client_info = pd.concat([client_info, clients]) if not client_info.empty else clients.copy()
    client_info = client_info.groupby(['Name', 'ID'])['Leave Date'].max().reset_index()
    
    return client_info

def add_ID_and_leave_date():
    client_info = pd.DataFrame()
    for year in sorted(os.listdir(settings.MEDIA_REMITTANCE)):
        filenames = sorted(os.listdir(os.path.join(settings.MEDIA_REMITTANCE, year)), key=lambda x: int(x.split('.')[0]))
        for filename in filenames:
            if '.csv' in filename:
                client_info = update_client_info_from_sefton_csv(client_info, year, filename)

    agg_df = client_info.groupby('ID')['Name'].count().reset_index()
    duplicate_ids = agg_df[agg_df['Name']>1]['ID']
    if not duplicate_ids.empty:
        print(client_info[client_info['ID'].isin(duplicate_ids)], '\n\n')
        # Remove duplicate residents, but keep the entry with the latest leave date
        client_info = client_info.sort_values(by=['ID', 'Leave Date'])
        client_info = client_info.groupby('ID').last().reset_index()[['Name', 'ID', 'Leave Date']]
    
    client_info.sort_values('Leave Date', inplace=True, ascending=False)
    recent_date = max(client_info['Leave Date'])
    print(client_info)
    
    query = Q()
    for row in client_info.iterrows():
        title, first, last = row[1].iloc[0].split(', ')

        query |= Q(title=title, first=first, last=last) # Obtain all residents not present before 2018

        res = resident.objects.get_or_create(title=title, first=first, last=last)[0]
        res.sefton_id = row[1].iloc[1]
        if row[1].iloc[2] != recent_date:
            res.leave_date = row[1].iloc[2]
        res.save()

    #Set leave date to 1 AD for all residents not present before 2018
    resident.objects.filter(~query).update(leave_date=date(1,1,1))

if __name__=='__main__':
    # add_year_and_batch_no_to_invoice_table()
    # use_existing_payment_filters()
    # merge_residents(61, 96)
    # add_ID_and_leave_date()
    add_customer_reference_numbers(6)
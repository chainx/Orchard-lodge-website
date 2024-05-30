import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from docx import Document
from random import randint
import pandas as pd
from shutil import make_archive
import pathlib

from backend.get_sefton_data import get_remittance_advice
from backend.file_utils import latest_filename

import django
django.setup()
from django.conf import settings
from main.models import resident, invoice

def main():
    latest_remittance = latest_filename(settings.MEDIA_REMITTANCE)
    invoices, sefton_payments, batch_number, folder = get_invoice_data_from_sefton_csv(latest_remittance)
    
    for inv in invoices:
        print(inv['invoice_number'], '   ', inv['Resident'].name, ' '*(30 - len(inv['Resident'].name)) + f"£{inv['total']/100:.2f}")
    print()
    for payment in sefton_payments:
        print(payment['Resident'].name, ' '*(30 - len(payment['Resident'].name)) + f"£{payment['total']/100:.2f}")

    write_invoices_and_update_db(invoices, batch_number, folder)

#==================================================================================================================================================================
def write_inovice(folder, date, Resident, sub_items, total, invoice_number, batch_number=None):

    document = Document(os.path.join(settings.MEDIA_INVOICES, 'INVOICE TEMPLATE.docx'))

    for paragraph in document.paragraphs:
        text_fields = {
            "NAME OF RECIPIENT": Resident.name,
            'INV_NO': invoice_number,
            "RES_REF": Resident.customer_ref_no,
            "DATE TODAY": date,
        }
        for text_field, text_input in text_fields.items():
            if paragraph.text.count(text_field)==1: 
                paragraph.text = paragraph.text.replace(text_field, text_input)

    count=0
    for debt in sub_items.itertuples():
        paragraph = document.tables[0].cell(0,0).paragraphs[7+count]

        reason=''
        if debt[3]!='' and debt[3]!='MA': 
            reason=' ('+debt[3]+')'
        paragraph.text='From ' + debt[2] + reason
        
        paragraph =  document.tables[0].cell(0,1).paragraphs[8+count]
        paragraph.text = u'\u00A3' + f'{debt[1]:.2f}'
        count+=1

    for paragraph in document.tables[0].cell(1,1).paragraphs:
        if paragraph.text.count('TOTAL')==1: paragraph.text=paragraph.text.replace('TOTAL', f'{total/100:.2f}')

    document.save(os.path.join(folder, f'{invoice_number} - {Resident.name}.docx'))

#==================================================================================================================================================================
def get_invoice_data_from_sefton_csv(filename): # Obtains data pertinent to writing invoices and updating the database

    date, year = datetime.now().strftime("%d %B %Y"), datetime.now().strftime("%Y")
    batch_number = int(os.path.basename(filename).split('.')[0])
    folder = os.path.join(settings.MEDIA_INVOICES, year, f'{batch_number}. {date}')
    invoice_number = max(invoice.objects.filter(obsolete=False).values_list('invoice_number', flat=True))

    df, payment_period = read_and_format_sefton_csv(filename)

    invoices, sefton_payments = [], []
    for index, df_row in df[['FormattedName', 'Sefton ID']].drop_duplicates().iterrows():
        
        res_name, sefton_id = df_row['FormattedName'], df_row['Sefton ID']
        res = get_or_add_resident(res_name, sefton_id)

        if inv := compile_personal_contributions_and_sefton_payments(res, df, batch_number, date, invoice_number, cost_or_income=1):
            invoice_number = "%05d" % (int(invoice_number)+1)
            invoices.append(inv)
        if payment := compile_personal_contributions_and_sefton_payments(res, df, batch_number, date, cost_or_income=0):
            sefton_payments.append(payment)
    
    invoices += compile_invoices_for_private_residents(payment_period, date, invoice_number)
    return invoices, sefton_payments, batch_number, folder

def compile_personal_contributions_and_sefton_payments(res, df, batch_number, date, invoice_number=None, cost_or_income=1):
    # cost_or_income = 1 for personal contributions and 0 for Sefton payments
    filt = (df['Sefton ID']==res.sefton_id) & (df['IsIncome']==cost_or_income)
    if not df.loc[filt].empty:
        row = {
            'Resident': res,
            'date' : date,
            'sub_items' : df.loc[filt][['Amount', 'PaymentItemDates', 'AdjustmentLabel']],
            'total' : round(df.loc[filt]['Amount'].sum()*100), # Amounts are stored in pennies in the database
            'batch_number': batch_number
        }
        if invoice_number:
            row['invoice_number'] = invoice_number

        return row

def compile_invoices_for_private_residents(payment_period, date, invoice_number):
    private_invoices = []
    residents = resident.objects.filter(current=True, private=True).order_by('last') # Add data for private residents
    for res in residents:
        invoice_number = "%05d" % (int(invoice_number)+1)
        row = {
            'Resident' : res,
            'date' : date,
            'sub_items' : pd.DataFrame({'Amount': res.private_rate, 'PaymentItemDates' : payment_period, 'AdjustmentLabel' : ''}, index=[0]),
            'total' : res.private_rate*100, # Amounts are stored in pennies in the database
            'invoice_number' : invoice_number
        }
        private_invoices.append(row)
    return private_invoices

#=============================================   UPDATE DB   ====================================================================================================

# Extract arguments for updating database from arguments for writing invoice, creates resident instance for new residents
def extract_invoice_args_for_db(invoice_data, batch_number, folder):
    invoice_data['filename'] = os.path.join(folder, f"{invoice_data['invoice_number']} - {invoice_data['Resident']}.docx")
    invoice_data['batch_number'] = batch_number
    invoice_data['date'] = datetime.strptime(invoice_data['date'],'%d %B %Y').strftime('%Y-%m-%d')
    invoice_data['year'] = datetime.strptime(invoice_data['date'],'%Y-%m-%d').year
    invoice_data.pop('sub_items')
    return invoice_data

def write_invoices_and_update_db(invoices, batch_number, folder):
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    
    year = datetime.now().strftime("%Y")
    if invoice.objects.filter(year=year, batch_number=batch_number):
        raise ValueError(f'There already exist entries in the database for batch number {batch_number} in {year}')

    for invoice_data in invoices:
        write_inovice(folder, **invoice_data) # Write invoice file locally
        invoice(**extract_invoice_args_for_db(invoice_data, batch_number, folder)).save() # Save invoices to the database

    make_archive(folder, "zip", folder)

#=============================================   UTILS   =======================================================================================================

def read_and_format_sefton_csv(filename):
    try:
        df = pd.read_csv(filename)
    except:
        df = pd.read_csv(filename, encoding='ISO-8859-1')
    
    df = df.fillna('')

    unusual_rows = df[df['ServiceTotalLabel']!='Total for Orchard Lodge Care Home']
    if not unusual_rows.empty:
        df = df[df['ServiceTotalLabel']=='Total for Orchard Lodge Care Home'] # Remove unusual rows

    payment_period = df.iloc[0]['ReportContext'].split('Payment Period from ')[1]

    format_function = lambda row: row['Person'].split()[0] + ',' + ', '.join(row['ClientName'].split(' (')[0].split(',')[::-1])
    df['FormattedName'] = df.apply(format_function, axis=1)
    df['Sefton ID'] = df['ClientName'].apply(lambda x: x.split(' (')[1][:-1])
    
    return df, payment_period

def get_or_add_resident(res_name, sefton_id, current=True, save=True):
    try:
        res = resident.objects.get(sefton_id=sefton_id)
    except:
        title, first, last = res_name.split(', ')
        if res := get_residents_with_similar_name(first, last):
            pass
        else:
            res = resident(title=title, first=first, last=last, sefton_id=sefton_id)
            res.current = current
            res.private = False
            res.customer_ref_no = generate_unique_customer_reference_number()
            if save:
                print(f'New resident added: {res.name} - {res.customer_ref_no}\n')
                res.save()
    if res.private:
        print(f'The private resident {res.name} has been added to the Sefton remittance advice\n')
    return res

def get_residents_with_similar_name(first, last):
    # Create a regex pattern that matches with any number of spaces or apostrophes between characters
    regex_pattern = r'(?i)^' + r'[\s\']*'.join(last.replace(' ','').replace("'", '')) + r'[\s\']*$'
    close_matches = resident.objects.filter(first__istartswith=first.split()[0], last__regex=regex_pattern)
    if len(close_matches)==1:
        print(f'The resident {first} {last} has been identified with the following close match:\n{close_matches[0]}\n')
        return close_matches[0]
    elif len(close_matches)>1:
        raise ValueError(f'Multiple close matches for {first} {last} in the database:\n {close_matches}\n')

def generate_unique_customer_reference_number():
    while True:
        customer_ref_no = ''.join([str(randint(0, 9)) for n in range(6)])
        if not resident.objects.filter(customer_ref_no=customer_ref_no):
            break # Keep generating customer reference numbers until a unique one is generated
    return customer_ref_no

#==================================================================================================================================================================

if __name__=='__main__':
    main()

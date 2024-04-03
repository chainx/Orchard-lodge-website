import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from docx import Document
import pandas as pd
from shutil import make_archive
import pathlib

from backend.get_sefton_data import get_remittance_advice
from backend.utils import get_latest

import django
django.setup()

from django.conf import settings
from main.models import resident, invoice

def main():
    latest_remittance = get_latest(settings.MEDIA_REMITTANCE)
    invoices, batch_number, folder = get_invoice_data_from_sefton_csv(latest_remittance)

    write_invoices_and_update_db(invoices, batch_number, folder)

#==============================================================================================================================================================================

def write_inovice(folder, date, Resident, sub_items, total, invoice_number, batch_number=None):

    document = Document(os.path.join(settings.MEDIA_INVOICES, 'INVOICE TEMPLATE.docx'))

    for paragraph in document.paragraphs:
        if paragraph.text.count("NAME OF RECIPIENT")==1: paragraph.text=paragraph.text.replace("NAME OF RECIPIENT",Resident)
        if paragraph.text.count("DATE TODAY")==1: paragraph.text=paragraph.text.replace("DATE TODAY",date)
        if paragraph.text.count("INVOICE NUMB")==1: paragraph.text=paragraph.text.replace("INVOICE NUMB",invoice_number)

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

    document.save(os.path.join(folder, invoice_number+' - '+Resident+'.docx'))

#==============================================================================================================================================================================

def get_invoice_data_from_sefton_csv(filename): # Obtains data pertinent to writing invoices and updating the database

    date, year = datetime.now().strftime("%d %B %Y"), datetime.now().strftime("%Y")
    
    batch_number = 1 # Default value, which is used at the start of a new year
    current_year_invoices = invoice.objects.filter(date__year=year)
    if current_year_invoices:
        batch_number = max(current_year_invoices.values_list('batch_number', flat=True)) + 1

    folder = os.path.join(settings.MEDIA_INVOICES, year, f'{batch_number}. {date}')

    invoice_number = max(invoice.objects.values_list('invoice_number', flat=True))

    df = pd.read_csv(filename).fillna('') # if ServiceTotalLabel != 'Total for Orchard Lodge Care Home' then it may contain a note from Sefton
    payment_period = df.iloc[0]['ReportContext'].split('Payment Period from ')[1]

    invoices=[]
    for res in df.Person.unique():
        filt = (df['Person']==res) & (df['IsIncome']==1) # Filter entries for each resident which are incomes (costs are paid by Sefton)
        if not df.loc[filt].empty:
            invoice_number = "%05d" % (int(invoice_number)+1)
            row = {
                'Resident' : res,
                'date' : date,
                'sub_items' : df.loc[filt][['Amount', 'PaymentItemDates', 'AdjustmentLabel']],
                'total' : int(df.loc[filt]['Amount'].sum()*100), # Amounts are stored in pennies in the database
                'invoice_number' : invoice_number,
                'batch_number': batch_number
            }
            invoices.append(row)

    residents = resident.objects.filter(current=True, private=True).order_by('last') # Add data for private residents
    for res in residents:
        invoice_number = "%05d" % (int(invoice_number)+1)
        row = {
            'Resident' : res.name,
            'date' : date,
            'sub_items' : pd.DataFrame({'Amount': res.private_rate, 'PaymentItemDates' : payment_period, 'AdjustmentLabel' : ''}, index=[0]),
            'total' : res.private_rate,
            'invoice_number' : invoice_number
        }
        invoices.append(row)
    
    return invoices, batch_number, folder

#==============================================================================================================================================================================

# Extract arguments for updating database from arguments for writing invoice, creates resident instance for new residents
def extract_invoice_args_for_db(invoice_data, batch_number, folder):
    name = invoice_data['Resident'].split()
    invoice_data['filename'] = folder+invoice_data['invoice_number']+' - '+invoice_data['Resident']+'.docx'
    invoice_data['batch_number'] = batch_number
    invoice_data['Resident'] = resident.objects.get_or_create(title=name[0], first=' '.join(name[1:-1]), last=name[-1])[0]
    invoice_data['date'] = datetime.strptime(invoice_data['date'],'%d %B %Y').strftime('%Y-%m-%d')
    invoice_data['year'] = datetime.strptime(invoice_data['date'],'%Y-%m-%d').year
    invoice_data['total'] *= 100 
    invoice_data.pop('sub_items')
    return invoice_data

def write_invoices_and_update_db(invoices, batch_number, folder):
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    
    for invoice_data in invoices:
        write_inovice(folder, **invoice_data) # Write invoice file locally
        # invoice(**extract_invoice_args_for_db(invoice_data, batch_number, folder)).save() # Save invoices to the database

    # make_archive(folder, "zip", folder)

#==============================================================================================================================================================================

if __name__=='__main__':
    main()

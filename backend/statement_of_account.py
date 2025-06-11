import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, date
from docx import Document
from copy import deepcopy
from shutil import make_archive

import django
django.setup()
from django.conf import settings
from main.models import resident, invoice, payment, CUTOFF_DATE

def main():
    produce_statements_of_account()
    produce_statements_of_account(recently_left=True)

#==================================================================================================================================================================

def produce_statements_of_account(recently_left=False):
    print(datetime.now().date().strftime('%B %Y'))
    
    folder = settings.MEDIA_INVOICES / f"Statements of account ({datetime.now().date().strftime('%B %Y')}){' recently left' if recently_left else ''}"
    if not recently_left:
        residents = resident.objects.filter(current=True)
    else:
        residents = resident.objects.filter(leave_date__gt=date(2024,10,1))

    os.makedirs(folder, exist_ok=True)
    
    count = 1
    for res in residents.order_by('last'):
        if res.total_owed() != 0:
            write_statement_of_account(folder, count, res)
            count+=1
        else:
            print(res.name)
            
    make_archive(folder, "zip", folder)

def write_statement_of_account(folder, count, res):

    document = Document(settings.MEDIA_INVOICES / 'STATEMENT OF ACCOUNT TEMPLATE.docx')

    text_fields = {
        "RES_NAME": res.name,
        "RES_REF": res.customer_ref_no,
        "DATE_TODAY": datetime.now().date().strftime('%d/%m/%Y'),
    }
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            for text_field, text_input in text_fields.items():
                if text_field in run.text:
                    run.text = run.text.replace(text_field, text_input)

    document.tables[0].cell(1, 0).text = str_total(res.total_invoiced())
    document.tables[0].cell(1, 1).text = str_total(res.total_payed())
    run = document.tables[0].cell(1, 2).paragraphs[0].add_run(str_total(res.total_owed()))
    run.bold = True

    for i, inv in enumerate(res.invoice_set.filter(obsolete=False).order_by('date').filter(date__gte=CUTOFF_DATE)):
        new_row = document.tables[1].add_row()
        copy_row_format(document.tables[1].rows[0], new_row)
        new_row.cells[0].text = inv.date.strftime('%d/%m/%Y')
        new_row.cells[1].text = inv.invoice_number
        new_row.cells[2].text = str(inv.batch_number)
        new_row.cells[3].text = str_total(inv.total)

    for i, pay in enumerate(res.payment_set.order_by('date').filter(date__gte=CUTOFF_DATE)):
        new_row = document.tables[2].add_row()
        copy_row_format(document.tables[2].rows[0], new_row)
        new_row.cells[0].text = pay.date.strftime('%d/%m/%Y')
        new_row.cells[1].text = str_total(pay.amount)
        new_row.cells[2].text = 'Bank transfer' if pay.type in ['Santander', 'RBS'] else pay.type

    document.save(os.path.join(folder, f'{count}. {res.name} - Statement of Account.docx'))

def copy_row_format(source_row, target_row):
    for source_cell, target_cell in zip(source_row.cells, target_row.cells):        
        tc_pr = source_cell._element.get_or_add_tcPr()
        new_tc_pr = target_cell._element.get_or_add_tcPr()
        for child in tc_pr.iterchildren():
            new_tc_pr.append(deepcopy(child))

def str_total(total):
    return u'\u00A3' + f'{total/100:,.2f}'

#==================================================================================================================================================================

if __name__=='__main__':
    main()
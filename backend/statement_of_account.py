import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, date
import pandas as pd
from docx import Document
from copy import deepcopy
from shutil import make_archive
import re

import django
django.setup()
from django.conf import settings
from main.models import resident, invoice, payment, CUTOFF_DATE

def main():
    produce_statements_of_account()
    produce_statements_of_account(recently_left=True)

#==================================================================================================================================================================

def produce_statements_of_account(recently_left=False):    
    filename = f"Statements of Account ({datetime.now().date().strftime('%d-%m-%Y')}){' Recently Left' if recently_left else ''}"
    folder = settings.MEDIA_INVOICES / filename
    if not recently_left:
        residents = resident.objects.filter(current=True)
    else:
        residents = resident.objects.filter(leave_date__gt=date(2025,2,1))
    resident_list = sorted(list(residents), key = lambda x: x.total_owed(), reverse=True)

    os.makedirs(folder, exist_ok=True)
    
    count = 1
    for res in resident_list:
        if res.total_owed() != 0:
            write_statement_of_account(folder, count, res)
            count+=1
        else:
            print(res.name)
    make_archive(folder, "zip", folder)

    produce_summary_table(resident_list, filename, recently_left)

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

def produce_summary_table(resident_list, filename, recently_left):
    owed_col_name = f"Total Owed ({datetime.now().date().strftime('%d %B')})"
    if not recently_left:
        df = pd.DataFrame([(res.name, res.total_owed()/100) for res in resident_list], columns=["Name", owed_col_name])
    else:
        df= pd.DataFrame([(res.name, res.total_owed()/100, res.leave_date) for res in resident_list], columns=["Name", owed_col_name, "Leave Date"])

    previous_filename = next(file for file in os.listdir(settings.MEDIA_INVOICES) if is_prev_excel_sheet(file, recently_left))
    previous_df = pd.read_excel(settings.MEDIA_INVOICES/previous_filename).iloc[:, 1:] # Removes index col
    
    combined_df = df.merge(previous_df, on="Name", how="left")
    combined_df.index = combined_df.index + 1

    with pd.ExcelWriter(settings.MEDIA_INVOICES/f"{filename}.xlsx", engine="xlsxwriter") as writer:
        combined_df.to_excel(writer, sheet_name="Sheet1")
        worksheet = writer.sheets["Sheet1"]

        base_fmt   = writer.book.add_format({"font_size": 13})
        pound_fmt  = writer.book.add_format({"num_format": "£#,##0.00", "font_size": 13})
        green_fmt  = writer.book.add_format({"num_format": "£#,##0.00", "font_color": "green", "font_size": 13})


        for col_idx, col in enumerate(combined_df.columns):
            col_idx+=1
            max_len = max(
                combined_df[col].astype(str).map(len).max(),
                len(str(col))
            )
            if pd.api.types.is_numeric_dtype(combined_df[col]):
                worksheet.set_column(col_idx, col_idx, max_len, pound_fmt)

                worksheet.conditional_format(
                    1, col_idx, len(combined_df), col_idx,
                    {
                        "type": "cell",
                        "criteria": "<=",
                        "value": 0,
                        "format": green_fmt,
                    }
                )
            else:
                worksheet.set_column(col_idx, col_idx, max_len, base_fmt)

def copy_row_format(source_row, target_row):
    for source_cell, target_cell in zip(source_row.cells, target_row.cells):        
        tc_pr = source_cell._element.get_or_add_tcPr()
        new_tc_pr = target_cell._element.get_or_add_tcPr()
        for child in tc_pr.iterchildren():
            new_tc_pr.append(deepcopy(child))

def str_total(total):
    return u'\u00A3' + f'{total/100:,.2f}'

def is_prev_excel_sheet(file, recently_left):
    if '.xlsx' in file and 'Statements of Account' in file and '~lock' not in file:
        if not recently_left:
            return True
        if 'Recently Left' in file:
            return True

#==================================================================================================================================================================

if __name__=='__main__':
    main()
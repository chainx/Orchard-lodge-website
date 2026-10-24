import os
import sys
import csv
from collections import Counter
from io import StringIO
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from math import isfinite
from docx import Document
from random import randint
import pandas as pd
from shutil import make_archive
import pathlib

from backend.get_sefton_data import get_remittance_advice
from backend.file_utils import latest_filename, file_num
from backend.draft_emails import draft_emails

import django
django.setup()
from django.conf import settings
from main.models import resident, invoice, sefton_payment

def main():
    # Test for invoice writing
    # debt = pd.DataFrame({'Amount': 100, 'PaymentItemDates' : '01/01/2025 - 28/01/2025', 'AdjustmentLabel' : ''}, index=[0])
    # write_inovice(settings.MEDIA_INVOICES, datetime.now().strftime("%d %B %Y"), resident.objects.get(id=100), debt, 10000, '015670', batch_number=10)
    # rewrite_invoice('inv_no', 'title first last', folder, invoices)
    # compile_summary_table(invoices, sefton_payments, folder)

    get_remittance_advice()

    latest_remittance = latest_filename(settings.MEDIA_REMITTANCE)
    invoices, sefton_payments, batch_number, folder = get_invoice_data_from_sefton_csv(latest_remittance)

    write_invoices_and_update_db(invoices, sefton_payments, batch_number, folder, update_db=True)
    draft_emails()

#=====================================================   READ AND WRITE DOCX FILES   ====================================================================================

def write_inovice(folder, date, Resident, sub_items, total, invoice_number, batch_number=None):
    document = Document(settings.MEDIA_INVOICES_TEMPLATES / 'INVOICE TEMPLATE.docx')

    tbl = document.tables[0]
    tbl.cell(0,0).paragraphs[0].text = tbl.cell(0,0).paragraphs[0].text.replace("NAME OF RECIPIENT", Resident.name)
    tbl.cell(0,1).paragraphs[0].text = tbl.cell(0,1).paragraphs[0].text.replace('INV_NO', invoice_number)
    tbl.cell(0,1).paragraphs[1].text = tbl.cell(0,1).paragraphs[1].text.replace("RES_REF", Resident.customer_ref_no)
    tbl.cell(0,1).paragraphs[2].text = tbl.cell(0,1).paragraphs[2].text.replace("DATE TODAY", date)
    
    desc_col, amount_col = document.tables[1].cell(0,0), document.tables[1].cell(0,1)
    desc_idx_offset, amount_idx_offset = 7, 8
    desc_idx_offset_min, amount_idx_offset_min = 3, 4
    max_rows = 20

    if len(sub_items) + desc_idx_offset > len(desc_col.paragraphs):
        print(f'Invoice for {Resident.name} has too many subitems, may have to be edited manually')
        offset = len(sub_items) - max_rows
        if offset >= 0:
            desc_idx_offset, amount_idx_offset = desc_idx_offset_min+offset, amount_idx_offset_min+offset
        else:
            print(f'{-offset} additional rows have been added')
            desc_idx_offset, amount_idx_offset = desc_idx_offset_min, amount_idx_offset_min
            for n in range(-offset):
                desc_col.add_paragraph()
                amount_col.add_paragraph()

    count=0
    for debt in sub_items.itertuples():
        paragraph = desc_col.paragraphs[desc_idx_offset+count]
        reason=' ('+debt[3]+')' if debt[3]!='' and debt[3]!='MA' else ''
        paragraph.text = f'From {debt[2]}{reason}'
        
        paragraph =  amount_col.paragraphs[amount_idx_offset+count]
        paragraph.text = u'\u00A3' + f'{debt[1]:.2f}'

        count+=1

    for paragraph in document.tables[1].cell(1,1).paragraphs:
        if paragraph.text.count('TOTAL')==1: paragraph.text=paragraph.text.replace('TOTAL', f'{total/100:.2f}')

    document.save(os.path.join(folder, f'{invoice_number} - {Resident.name}.docx'))

def rewrite_invoice(invoice_number, resident_name, folder, invoices):
    invoice = [invoice for invoice in invoices if invoice['Resident'].name == resident_name][0]
    invoice['invoice_number'] = invoice_number
    write_inovice(folder, **invoice)

#===============================================   EXTRACTING DATA FROM CSV   ===================================================================================

def get_invoice_data_from_sefton_csv(filename, save_new_residents=True): # Obtains data pertinent to writing invoices and updating the database
    df, payment_period = read_and_format_sefton_csv(filename)

    date, year = datetime.now().strftime("%d %B %Y"), datetime.now().strftime("%Y")
    batch_number = file_num(os.path.basename(filename))
    os.makedirs(os.path.join(settings.MEDIA_INVOICES, year), exist_ok=True)
    folder = os.path.join(settings.MEDIA_INVOICES, year, f'{batch_number}. {date}')
    invoice_number = max(invoice.objects.filter(obsolete=False).values_list('invoice_number', flat=True))
    invoice_number = "%05d" % (int(invoice_number)+1)

    invoices, sefton_payments = [], []
    preview_resident_ids = set()
    for index, df_row in df[['FormattedName', 'Sefton ID']].drop_duplicates().iterrows():
        
        res_name, sefton_id = df_row['FormattedName'], df_row['Sefton ID']
        res = get_or_add_resident(
            res_name, sefton_id, save=save_new_residents,
            excluded_resident_ids=preview_resident_ids,
        )
        if not save_new_residents and res.pk is not None:
            # Reserve this match in memory because preview does not save its ID.
            preview_resident_ids.add(res.pk)

        invoice_total = 0 # Subtracted from Sefton cost to find total paid by Sefton
        if inv := compile_personal_contributions_and_sefton_payments(res, df, batch_number, date, invoice_number, cost_or_income=1):
            invoice_number = "%05d" % (int(invoice_number)+1)
            invoice_total = inv['total']
            invoices.append(inv)
        if payment := compile_personal_contributions_and_sefton_payments(res, df, batch_number, payment_period, cost_or_income=0, invoice_total=invoice_total):
            sefton_payments.append(payment)
    
    invoices += compile_invoices_for_private_residents(payment_period, batch_number, date, invoice_number)
    return invoices, sefton_payments, batch_number, folder

def compile_personal_contributions_and_sefton_payments(res, df, batch_number, date, invoice_number=None, cost_or_income=1, invoice_total=0):
    # cost_or_income = 1 for personal contributions and 0 for Sefton payments
    filt = (df['Sefton ID']==res.sefton_id) & (df['IsIncome']==cost_or_income)
    if df.loc[filt].empty:
        return
    if abs(df.loc[filt]['Amount'].sum())<1:
        return # Don't write invoices for less than £1
    row = {
        'Resident': res,
        'date' : date,
        'sub_items' : df.loc[filt][['Amount', 'PaymentItemDates', 'AdjustmentLabel']],
        'total' : round(df.loc[filt]['Amount'].sum()*100) - invoice_total, # Amounts are stored in pennies in the database
        'batch_number': batch_number
    }
    if invoice_number:
        row['invoice_number'] = invoice_number

    return row

def compile_invoices_for_private_residents(payment_period, batch_number, date, invoice_number):
    private_invoices = []
    residents = resident.objects.filter(current=True, private=True).order_by('last') # Add data for private residents
    for res in residents:
        invoice_number = "%05d" % (int(invoice_number)+1)
        row = {
            'Resident' : res,
            'date' : date,
            'sub_items' : pd.DataFrame({'Amount': res.private_rate, 'PaymentItemDates' : payment_period, 'AdjustmentLabel' : ''}, index=[0]),
            'total' : res.private_rate*100, # Amounts are stored in pennies in the database
            'batch_number': batch_number,
            'invoice_number' : invoice_number
        }
        private_invoices.append(row)
    return private_invoices

#=============================================   UPDATE DB   ====================================================================================================

# Extract arguments for updating database from arguments for writing invoice, creates resident instance for new residents
def extract_invoice_args_for_db(invoice_data, folder):
    invoice_data['filename'] = os.path.join(folder, f"{invoice_data['invoice_number']} - {invoice_data['Resident']}.docx")
    invoice_data['date'] = datetime.strptime(invoice_data['date'], '%d %B %Y')
    invoice_data['year'] = invoice_data['date'].year
    invoice_data.pop('sub_items')
    return invoice_data

def extract_payment_args_for_db(payment):
    payment['date'] = datetime.strptime(payment['date'].split(' to ')[1], '%d/%m/%Y').date()
    payment['year'] = payment['date'].year
    payment.pop('sub_items')
    return payment

def write_invoices_and_update_db(invoices, sefton_payments, batch_number, folder, update_db=True):    
    year = datetime.now().strftime("%Y")
    if invoice.objects.filter(year=year, batch_number=batch_number):
        raise ValueError(f'There already exist entries in the database for batch number {batch_number} in {year}')

    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)

    for invoice_data in invoices:
        write_inovice(folder, **invoice_data) # Write invoice file locally
        if update_db:
            invoice(**extract_invoice_args_for_db(invoice_data, folder)).save() # Save invoices to the database
    if update_db:
        for payment in sefton_payments:
            sefton_payment(**extract_payment_args_for_db(payment)).save()

    make_archive(folder, "zip", folder)

def compile_summary_table(invoices, sefton_payments, folder, print_table=False):
    invoices_df = pd.DataFrame(invoices, columns=['Resident', 'total'])
    payments_df = pd.DataFrame(sefton_payments, columns=['Resident', 'total'])
    df = pd.merge(invoices_df, payments_df, on='Resident', how='outer')
    df = df.rename(columns={'total_x': 'Invoice total', 'total_y': 'Sefton contribution'})
    df[['Invoice total', 'Sefton contribution']] /= 100
    df.index = df.reset_index(drop=True).index + 1
    df.to_excel(folder+'.xlsx')
    if print_table:
        print(df)

#===================================   READ AND ERROR CORRECT CSV   =========================================================================================

def read_and_format_sefton_csv(filename):
    # Preserve text such as "NA" and validate numbers before converting them.
    contents = filename.read() if hasattr(filename, 'read') else pathlib.Path(filename).read_bytes()
    if isinstance(contents, bytes):
        try:
            contents = contents.decode('utf-8-sig')
        except UnicodeDecodeError:
            contents = contents.decode('ISO-8859-1')
    contents = contents.removeprefix('\ufeff')
    try:
        # pandas renames duplicate headers (e.g. Amount -> Amount.1), so inspect
        # the original header before loading the table. Skip leading blank lines.
        header = next(
            (row for row in csv.reader(StringIO(contents), strict=True)
             if row and (len(row) > 1 or row[0].strip())),
            [],
        )
        duplicates = [name for name, count in Counter(header).items() if count > 1]
        if duplicates:
            raise ValueError(f"Invalid Sefton CSV: duplicate column names: {', '.join(duplicates)}")
        df = pd.read_csv(StringIO(contents), dtype=str, keep_default_na=False)
    except (csv.Error, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise ValueError(f'Invalid Sefton CSV: {error}') from error

    required_columns = (
        'ServiceTotalLabel', 'ReportContext', 'Person', 'ClientName',
        'Amount', 'IsIncome', 'PaymentItemDates', 'AdjustmentLabel',
    )
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Invalid Sefton CSV: missing required columns: {', '.join(missing)}")
    if df.empty:
        raise ValueError('Invalid Sefton CSV: no data rows')
    if not isinstance(df.index, pd.RangeIndex):
        raise ValueError('Invalid Sefton CSV: rows contain more fields than the header')

    def reject_rows(column, invalid, expected):
        if invalid.any():
            # Retain source indices when filtering to identify CSV row numbers.
            rows = ', '.join(str(index + 2) for index in df.index[invalid][:10])
            raise ValueError(
                f'Invalid Sefton CSV: {column} must be {expected} (CSV rows {rows})'
            )

    reject_rows('ServiceTotalLabel', df['ServiceTotalLabel'].str.strip().eq(''), 'non-empty text')
    df = df.loc[df['ServiceTotalLabel'].eq('Total for Orchard Lodge Care Home')].copy()
    if df.empty:
        raise ValueError('Invalid Sefton CSV: no rows for Orchard Lodge Care Home')

    # Compare every source column before numeric conversion. Matching invoice
    # fields alone can represent distinct payments with different source metadata.
    duplicates = df.duplicated(keep=False)
    if duplicates.any():
        rows = ', '.join(str(index + 2) for index in df.index[duplicates][:10])
        raise ValueError(
            f'Invalid Sefton CSV: duplicate rows (CSV rows {rows}); '
            'review the source remittance before importing'
        )

    for column in ('ReportContext', 'Person', 'ClientName', 'PaymentItemDates'):
        reject_rows(column, df[column].str.strip().eq(''), 'non-empty text')

    for column in ('Amount', 'IsIncome'):
        numbers = pd.to_numeric(df[column], errors='coerce')
        if column == 'Amount':
            reject_rows(column, ~numbers.map(isfinite), 'a finite number')
        else:
            reject_rows(column, ~numbers.isin([0, 1]), '0 or 1')
        df[column] = numbers

    # These structures are used below to extract the resident and payment dates.
    clients = df['ClientName'].str.extract(
        r'\A(?P<last>[^,()\s][^,()]*), (?P<first>[^,()\s][^,()]*) '
        r'\((?P<sefton_id>[^()\s]+)\)\Z',
    )
    reject_rows(
        'ClientName',
        clients.isna().any(axis=1),
        'in the format "Surname, First name (Sefton ID)"',
    )
    clients['first'] = clients['first'].str.strip()
    clients['last'] = clients['last'].str.strip()

    item_periods = df['PaymentItemDates'].str.extract(
        r'\A(\d{2}/\d{2}/(?:\d{4}|\d{2})) (?:to|-) '
        r'(\d{2}/\d{2}/(?:\d{4}|\d{2}))\Z',
    )
    item_dates = [
        pd.to_datetime(item_periods[column], format='%d/%m/%Y', errors='coerce').fillna(
            pd.to_datetime(item_periods[column], format='%d/%m/%y', errors='coerce')
        )
        for column in (0, 1)
    ]
    reject_rows(
        'PaymentItemDates',
        item_dates[0].isna() | item_dates[1].isna() | (item_dates[0] > item_dates[1]),
        'a valid date range with the start on or before the end '
        '(DD/MM/YY or DD/MM/YYYY, separated by " to " or " - ")',
    )
    periods = df['ReportContext'].str.extract(
        r'Payment Period from (\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})$',
        expand=True,
    )
    start = pd.to_datetime(periods[0], format='%d/%m/%Y', errors='coerce')
    end = pd.to_datetime(periods[1], format='%d/%m/%Y', errors='coerce')
    reject_rows(
        'ReportContext', start.isna() | end.isna() | (start > end),
        'a valid "Payment Period from DD/MM/YYYY to DD/MM/YYYY" date range',
    )
    payment_periods = periods[0] + ' to ' + periods[1]
    if payment_periods.nunique() != 1:
        raise ValueError('Invalid Sefton CSV: ReportContext contains inconsistent payment periods')
    payment_period = payment_periods.iloc[0]

    # Some exports omit the title: Person then begins with the given name.
    # Extract the actual name and ID from the validated ClientName captures.
    person_first_word = df['Person'].str.split().str[0]
    given_first_word = clients['first'].str.split().str[0]
    titles = person_first_word.where(
        person_first_word.str.casefold() != given_first_word.str.casefold(), ''
    )
    df['FormattedName'] = titles + ', ' + clients['first'] + ', ' + clients['last']
    df['Sefton ID'] = clients['sefton_id']

    # Each name/ID pair is processed separately by the invoice compiler. Multiple
    # names for the same ID would cause its amounts to be invoiced more than once.
    names_per_id = df.groupby('Sefton ID')['FormattedName'].transform('nunique')
    reject_rows('Sefton ID', names_per_id.gt(1), 'associated with a single resident name')
    
    return df, payment_period

#=============================================   UTILS   =======================================================================================================

def get_or_add_resident(res_name, sefton_id=None, current=True, private=False, save=True, excluded_resident_ids=()):
    new_res_created = False
    res = None
    if sefton_id:
        try:
            res = resident.objects.get(sefton_id=sefton_id)
        except resident.DoesNotExist:
            pass
    if res is None:
        title, first, last = res_name.split(', ')
        if res := get_residents_with_similar_name(
            first, last, unassigned_only=bool(sefton_id),
            excluded_resident_ids=excluded_resident_ids,
        ):
            if sefton_id and not res.sefton_id:
                res.sefton_id = sefton_id
                if save:
                    res.save(update_fields=['sefton_id'])
        else:
            new_res_created = True
            res = resident(title=title, first=first, last=last, sefton_id=sefton_id)
            res.current = current
            res.private = private
            res.customer_ref_no = generate_unique_customer_reference_number()
            if save:
                print(f'New resident added: {res.name} - {res.customer_ref_no}\n')
                res.save()
            else:
                print(f'New resident: {res.name} - {res.customer_ref_no}, NOT SAVED!\n')
    if res.private and not new_res_created:
        print(f'The private resident {res.name} has been added to the Sefton remittance advice\n')
    if not res.current and not new_res_created:
        print(f'The former resident {res.name} has been added to the Sefton remittance advice\n')
    return res

def get_residents_with_similar_name(first, last, verbose=True, unassigned_only=False, excluded_resident_ids=()):
    # Create a regex pattern that matches with any number of spaces or apostrophes between characters
    regex_pattern = r'(?i)^' + r'[\s\']*'.join(last.replace(' ','').replace("'", '')) + r'[\s\']*$'
    close_matches = resident.objects.filter(first__istartswith=first.split()[0], last__regex=regex_pattern)
    if unassigned_only:
        # A matching name cannot override a different council identity. Filter
        # before checking ambiguity so already assigned residents do not count.
        close_matches = close_matches.filter(sefton_id__isnull=True) | close_matches.filter(sefton_id='')
    if excluded_resident_ids:
        close_matches = close_matches.exclude(pk__in=excluded_resident_ids)
    if len(close_matches)==1:
        if verbose:
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

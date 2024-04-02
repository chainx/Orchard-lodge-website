import pandas as pd
from datetime import datetime
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import django
django.setup()

from django.conf import settings
from django.db.models import F, Value
from django.db.models.functions import Concat

from main.models import payment
from main.models import resident
from backend.get_santander_data import scrape_santander_bank_statements

santander_file_path = os.path.join(settings.MEDIA_PAYMENTS, 'Santander')
santander_file = os.path.join(settings.MEDIA_PAYMENTS, 'Santander.xlsx')

def main():
    excel_payments = pd.read_excel(santander_file)
    from_date = datetime.strptime(excel_payments.iloc[0].Date, '%d/%m/%Y').date()

    scrape_santander_bank_statements(from_date, datetime.now().date())                          
    downloaded_payments = combine_downloaded_files(santander_file_path, delete_used_files=True)
    excel_payments = combine_with_local_excel_file(excel_payments, downloaded_payments, from_date)
    check_santander_file_consistent(excel_payments)
    excel_payments.to_excel(santander_file, index=False)

    update_db(downloaded_payments, from_date)

def match_payments_to_resident(resident_id, filters):
    for filter in filters.split(';'):
        matching_payments = payment.objects.filter(description__icontains=filter).exclude(Resident_id=resident_id)
        already_matched_payments = matching_payments.filter(Resident_id__isnull=False)
        if already_matched_payments:
            other_resident_matches = set(already_matched_payments.values_list('Resident_id', flat=True))
            return other_resident_matches
        matching_payments.update(Resident_id=resident_id)
    resident.objects.filter(id=resident_id).update(filters=filters.lower())

def update_db(downloaded_payments, from_date):
    new_payments = get_new_payments(downloaded_payments, from_date)
    for index, payment_ in new_payments[::-1].iterrows():
        payment(**extract_payment_kwargs_for_db(payment_, 'Santander')).save()

def extract_payment_kwargs_for_db(payment, bank):
    kwargs = {
        'date': payment.date,
        'description': payment.description,
        'amount': convert_to_pennies(payment.amount),
        'matched': False,
        'type' : bank,
    }
    return kwargs

def get_new_payments(downloaded_payments, from_date):
    downloaded_payments = downloaded_payments[downloaded_payments['Money in'].notnull()][['Date', 'Description', 'Money in']]
    downloaded_payments['Date'] = pd.to_datetime(downloaded_payments['Date'], format='%d/%m/%Y').dt.date
    downloaded_payments = downloaded_payments.rename(columns=excel_to_db_cols )

    payments_db = payment.objects.filter(date=from_date)
    if not payments_db.values(): return downloaded_payments # Handles case where payments_db is empty
    payments_db = pd.DataFrame(list(payments_db.values()))[['date', 'description', 'amount']]

    match_cols = ['date', 'description', 'amount']
    outer_join = payments_db.merge(downloaded_payments, on=match_cols, how='outer', indicator=True)
    return outer_join[outer_join._merge=='right_only'].drop('_merge', axis='columns')

# ============================================================   ERROR CORRECTION ================================================================================

def check_santander_file_consistent(excel_payments):
    previous_balance = convert_to_pennies(excel_payments.iloc[-1].Balance)
    for index, row in excel_payments.iloc[:-1][::-1].iterrows():
        next_balance = convert_to_pennies(row.Balance)

        if isinstance(row['Money Out'], str):
            expected_balance = previous_balance - convert_to_pennies(row['Money Out'])
        elif isinstance(row['Money in'], str):
            expected_balance = previous_balance + convert_to_pennies(row['Money in'])
        else:
            raise ValueError(f'There is an entry with no money in or out:\n{row}')

        if next_balance != expected_balance:
            raise ValueError(f'There is a mismatch between the transaction cols and the balance col:\n {prev_row}\n{row}')
        previous_balance = next_balance
        prev_row = row

    print('No inconsistencies between the transaction cols and the balance col')

#============================================================= COMBING STATEMENTS ===============================================================================

def combine_with_local_excel_file(excel_payments, downloaded_payments, from_date):
    old_payments = excel_payments[pd.to_datetime(excel_payments.Date, format='%d/%m/%Y').dt.date.lt(from_date)]
    return pd.concat([downloaded_payments, old_payments], ignore_index=True)

def combine_downloaded_files(file_path, check_table_formats=True, delete_used_files=True):
    files = [os.path.join(file_path, file) for file in os.listdir(file_path) if file.endswith('.xls') and '.~lock.' not in file]
    payments_dict = {}
    for filename in files:
        if 'Santander' in file_path:
            payments, period = read_and_format_santander_statement(filename, check_table_formats)
        elif 'RBS' in file_path:
            payments, period = read_and_format_rbs_statement(filename, check_table_formats)
        else:
            raise ValueError(f'Bank statement type cannot be determined from file path: {file_path}')
        payments_dict[period[1]] = payments

    sorted_dates = sorted(payments_dict.keys())
    combined_payments = payments_dict[sorted_dates[0]]
    for date in sorted_dates[1:]:
        combined_payments = pd.concat([payments_dict[date], combined_payments], axis='rows')

    if not combined_payments[combined_payments.duplicated()].empty:
        raise ValueError(f'There are duplicate payments indicating a possible error:\n\n{combined_payments[combined_payments.duplicated()]}')
    
    if delete_used_files:
        for file in files:
            os.remove(file)
    
    return combined_payments

def read_and_format_santander_statement(filename, check_table_formats=True):
    payments = pd.read_html(filename)[0]
    payments = payments.dropna(axis='columns', how='all').dropna(axis='rows', how='all')
    
    if payments.iloc[0].values[0] != 'Transactions' or '  to  ' not in payments.iloc[1].values[1]:
        print(payments.head())
        raise ValueError('File format not as expected')
    period = payments.iloc[1].values[1].split('  to  ')
    period = [datetime.strptime(date, '%d/%m/%Y').date() for date in period]
    payments = payments[2:]

    expected_cols = ['Date', 'Description', 'Money in', 'Money Out', 'Balance']
    cols = payments.iloc[0]
    payments = pd.DataFrame(payments.values[1:], columns=cols)
    payments.columns.name = None
    if check_table_formats and list(payments.columns) != expected_cols:
        unexpected_cols = [col for col in list(payments.columns) if col not in expected_cols]
        unexpected_values = payments[unexpected_cols].dropna().values
        input(f'There are additional cols with the following values:\n\n{unexpected_values}\n\nIs it okay to discard these cols?')
        payments = payments[expected_cols]

    return payments, period

def read_and_format_rbs_statement(filename):
    pass

#============================================================= UTILS ===============================================================================

excel_to_db_cols = {
    'Date': 'date',
    'Description': 'description',
    'Money in': 'amount'
}

def convert_to_pennies(amount):
    return int(amount.split()[1].replace(',','').replace('.',''))

#=====================================================================================================================================================================

if __name__=='__main__':
    main()
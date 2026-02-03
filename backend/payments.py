import pandas as pd
from datetime import datetime, date
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import django
django.setup()

from django.conf import settings
from django.db.models import F, Value, Q, Sum
from django.db.models.functions import Concat

from main.models import resident, payment, CUTOFF_DATE
from backend.get_santander_data import scrape_santander_bank_statements

santander_file_path = os.path.join(settings.MEDIA_PAYMENTS, 'Santander')
santander_file = os.path.join(settings.MEDIA_PAYMENTS, 'Santander.xlsx')

def main():
    excel_payments = pd.read_excel(santander_file)

    from_date = datetime.strptime(excel_payments.iloc[0].Date, '%d/%m/%Y').date()
    scrape_santander_bank_statements(from_date, datetime.now().date())                          
    downloaded_payments = format_and_combine_downloaded_files(santander_file_path, delete_used_files=True)
    excel_payments = combine_with_local_excel_file(excel_payments, downloaded_payments, from_date)
    check_santander_file_consistent(excel_payments)
    excel_payments.to_excel(santander_file, index=False)

    new_payments = get_new_payments(excel_payments)
    print(new_payments)
    add_payments_to_db(new_payments)
    match_payments_wtih_existing_payment_filters()

# ============================================================   UPDATE DB   ================================================================================


def add_payments_to_db(new_payments, bank='Santander'):
    if new_payments.empty:
        return
    if new_payments.iloc[0].date > new_payments.iloc[-1].date:
        new_payments = new_payments.iloc[::-1]
    for index, payment_ in new_payments.iterrows():
        payment(**extract_payment_kwargs_for_db(payment_, bank)).save()

def extract_payment_kwargs_for_db(payment, bank):
    kwargs = {
        'date': payment.date,
        'description': payment.description,
        'amount': payment.amount,
        'matched': False,
        'type' : bank,
    }
    return kwargs

def get_new_payments(excel_payments, bank='Santander'):
    # Filter for payments and reformat so that schema matches that from DB
    excel_payments = excel_payments[excel_payments['Money in'].notnull()]
    excel_payments = excel_payments[excel_to_db_cols.keys()]
    excel_payments['Money in'] = excel_payments['Money in'].apply(convert_to_pennies)
    excel_payments['Description'] = excel_payments['Description'].apply(str.upper)
    excel_payments['Date'] = pd.to_datetime(excel_payments['Date'], format='%d/%m/%Y').dt.date
    excel_payments = excel_payments.rename(columns=excel_to_db_cols )

    db_payments = payment.objects.filter(type=bank)
    if not db_payments.values(): return excel_payments # Handles case where db_payments is empty
    db_payments = pd.DataFrame(list(db_payments.values()))
    db_payments = db_payments[excel_to_db_cols.values()].astype('object') # Project columns and convert col types to match excel schema

    match_cols = list(excel_to_db_cols.values())
    outer_join = db_payments.merge(excel_payments, on=match_cols, how='outer', indicator=True)
    if not outer_join[outer_join._merge=='left_only'].empty:
        raise ValueError(f'There are {bank} payments in the DB with no matching payment in the local {bank} Excel file!')
    
    return outer_join[outer_join._merge=='right_only'].drop('_merge', axis='columns')

# ============================================================   MATCH PAYMETNS TO RESIDENTS   ================================================================================

def match_payments_wtih_existing_payment_filters(verbose=True):
    for res in resident.objects.all():
        res_filters = res.filters.split(';') if res.filters else []
        for res_filter in res_filters:
            match_payments_to_resident(res.id, res_filters, res.name, verbose)

def match_payments_to_resident(resident_id, filters, resident_name, verbose=True):
    for filter in filters:
        matching_payments = payment.objects.filter(description__icontains=filter).exclude(Resident_id=resident_id)
        already_matched_payments = matching_payments.filter(Resident_id__isnull=False)
        if already_matched_payments:
            other_resident_matches = set(already_matched_payments.values_list('Resident_id', flat=True))
            error_msg = f'The following payments have been matched to {resident_name}:\n\n{already_matched_payments}\n\n'
            error_msg += f'But these payments have already been matched to the following residents:\n\n{other_resident_matches}'
            raise ValueError(error_msg)
        if verbose and matching_payments:
            print(f'\nThe following payments will be matched to {resident_name}:\n{matching_payments}')
        matching_payments.update(Resident_id=resident_id)

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

def format_and_combine_downloaded_files(file_path, check_table_formats=True, delete_used_files=True):
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

def find_all_cash_payments(cutoff_date=CUTOFF_DATE):
    payments = payment.objects.filter(Q(date__gt=cutoff_date) & Q(type='Cash'))
    total = payments.aggregate(total=Sum('amount'))['total']
    print(f"£{total/100:,.2f}")
    #residents Q(leave_date__gt=cutoff_date | Q(current=True)
    # for res in residents:
    #     if len(res.payment_set.filter(type='Cash'))>0:
    #         leave_date = res.leave_date if res.leave_date else ''
    #         print(res.name, len(res.payment_set.filter(type='Cash')), leave_date)

#=====================================================================================================================================================================

if __name__=='__main__':
    main()
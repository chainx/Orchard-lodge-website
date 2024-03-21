import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from datetime import datetime

import django
django.setup()

from django.conf import settings
from main.models import payment

def main():
    # file_path = os.path.join(settings.MEDIA_PAYMENTS, 'Santander')
    # combined_payments = combine_statements(file_path)
    # combined_payments.to_excel(os.path.join(settings.MEDIA_PAYMENTS, 'Santander.xlsx'))

    payments = pd.read_excel(os.path.join(settings.MEDIA_PAYMENTS, 'Santander.xlsx'), index_col='Date')
    print()

#==============================================================================================================================================================================

def read_and_format_santander_statement(filename):
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
    if list(payments.columns) != expected_cols:
        unexpected_cols = [col for col in list(payments.columns) if col not in expected_cols]
        unexpected_values = payments[unexpected_cols].dropna().values
        input(f'There are additional cols with the following values:\n\n{unexpected_values}\n\nIs it okay to discard these cols?')
        payments = payments[expected_cols]

    payments.set_index('Date', inplace=True)

    return payments, period

def read_and_format_rbs_statement(filename):
    pass

def combine_statements(file_path):
    files = [os.path.join(file_path, file) for file in os.listdir(file_path) if '.xls' in file and '.~lock.' not in file]
    payments_dict = {}
    for filename in files:
        if 'Santander' in file_path:
            payments, period = read_and_format_santander_statement(filename)
        elif 'RBS' in file_path:
            payments, period = read_and_format_rbs_statement(filename)
        else:
            raise ValueError(f'Bank statement type cannot be determined from file path: {file_path}')
        payments_dict[period[1]] = payments

    sorted_dates = sorted(payments_dict.keys())
    combined_payments = payments_dict[sorted_dates[0]]
    for date in sorted_dates[1:]:
        combined_payments = pd.concat([payments_dict[date], combined_payments], axis='rows')

    if not combined_payments[combined_payments.duplicated()].empty:
        raise ValueError(f'There are duplicate payments indicating a possible error:\n\n{combined_payments[combined_payments.duplicated()]}')
    
    return combined_payments

#==============================================================================================================================================================================

if __name__=='__main__':
    main()
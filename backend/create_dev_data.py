import os
import json
import argparse
from pathlib import Path

os.environ['DJANGO_SETTINGS_MODULE'] = 'OrchardLodge.settings.development'

import django
django.setup()

import pandas as pd
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils.dateparse import parse_datetime

from backend.invoices import write_inovice
from backend.statement_of_account import produce_statements_of_account
from main.models import global_variables, invoice, payment, resident, sefton_action_item, sefton_login_details, sefton_payment

DEV_USERNAME = 'orchard-dev'
DEV_PASSWORD = 'orchard-dev-password'


def main(produce_files=False):
    reset_database()
    create_global_variables()
    if produce_files:
        create_dummy_secret_files()
    create_residents()
    create_invoices(produce_files)
    create_payments()
    create_sefton_payments(produce_files)
    create_sefton_action_items()
    if produce_files:
        produce_statements_of_account()
    create_dev_user()
    create_dummy_login_details()

    print(f'Seeded fresh development database at {settings.DATABASES["default"]["NAME"]}')
    print(f'Development login: {DEV_USERNAME} / {DEV_PASSWORD}')
    

def reset_database():
    db_path = Path(settings.DATABASES['default']['NAME'])
    if db_path.exists():
        db_path.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    call_command('migrate', skip_checks=True, verbosity=0)


def create_global_variables():
    global_variables.load().save()


def create_dummy_secret_files():
    settings.SECRET_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

    santander_login = {
        'SANTANDER_COOKIE_DIR': 'Santander cookies',
        'AGENT_STRING': 'Orchard Lodge development',
        'BANK_DETAILS': {
            'PID': '0000000000',
            'SECURITY_NUMBER': '000000',
        },
    }
    email_details = {
        'EMAIL_ADDRESS': 'finance@example.com',
        'EMAIL_PASSWORD': 'dummy-password',
        'CC': 'accounts@example.com',
        'BCC': 'audit@example.com',
    }

    with open(settings.SECRET_MEDIA_ROOT / 'Santander_login.json', 'w') as secret_file:
        json.dump(santander_login, secret_file, indent=2)
        secret_file.write('\n')

    with open(settings.SECRET_MEDIA_ROOT / 'Email_details.json', 'w') as secret_file:
        json.dump(email_details, secret_file, indent=2)
        secret_file.write('\n')


def create_residents():
    rows = [
        {
            'id': 201,
            'title': 'Mr',
            'first': 'Arthur',
            'last': 'Test',
            'email': 'arthur.test@example.com',
            'email_name': 'Mr Test',
            'current': True,
            'private': False,
            'private_rate': 0,
            'filters': 'ARTHUR TEST',
            'sefton_id': 'DEV-SEFTON-001',
            'customer_ref_no': '900201',
            'start_date': '2024-01-08',
        },
        {
            'id': 202,
            'title': 'Ms',
            'first': 'Bella',
            'last': 'Noemail',
            'email': '',
            'email_name': 'Bella',
            'current': True,
            'private': False,
            'private_rate': 0,
            'filters': 'BELLA NOEMAIL',
            'sefton_id': 'DEV-SEFTON-002',
            'customer_ref_no': '900202',
            'start_date': '2024-02-12',
        },
        {
            'id': 203,
            'title': 'Mrs',
            'first': 'Carla',
            'last': 'Private',
            'email': 'carla.private@example.com',
            'email_name': 'Carla',
            'current': True,
            'private': True,
            'private_rate': 1200,
            'filters': 'CARLA PRIVATE',
            'sefton_id': '',
            'customer_ref_no': '900203',
            'start_date': '2023-09-01',
        },
        {
            'id': 204,
            'title': 'Mr',
            'first': 'Derek',
            'last': 'Former',
            'email': 'derek.former@example.com',
            'email_name': 'Derek',
            'current': False,
            'private': False,
            'private_rate': 0,
            'filters': 'DEREK FORMER',
            'sefton_id': 'DEV-SEFTON-004',
            'customer_ref_no': '900204',
            'start_date': '2022-04-04',
            'leave_date': '2025-03-14',
        },
        {
            'id': 205,
            'title': 'Miss',
            'first': 'Eva',
            'last': 'Cash',
            'email': 'eva.cash@example.com',
            'email_name': 'Eva',
            'current': True,
            'private': False,
            'private_rate': 0,
            'filters': 'EVA CASH',
            'sefton_id': 'DEV-SEFTON-005',
            'customer_ref_no': '900205',
            'start_date': '2025-05-01',
        },
        {
            'id': 206,
            'title': 'Dr',
            'first': 'Frank',
            'last': 'Family',
            'email': 'frank.family@example.com',
            'email_name': 'Dr Family',
            'current': True,
            'private': True,
            'private_rate': 950,
            'filters': 'FRANK FAMILY',
            'sefton_id': '',
            'customer_ref_no': '900206',
            'start_date': '2025-11-17',
        },
    ]

    for row in rows:
        resident.objects.create(**row)


def create_invoices(produce_files):
    invoice_folder = settings.MEDIA_INVOICES / '2026' / '4. 27 May 2026'
    rows = [
        (301, 201, '02001', '01/05/2026', '28/05/2026', 45000, False, False),
        (302, 202, '02002', '01/05/2026', '28/05/2026', 37500, False, False),
        (303, 203, '02003', '01/05/2026', '31/05/2026', 120000, False, False),
        (304, 205, '02004', '01/05/2026', '14/05/2026', 21550, False, True),
        (305, 206, '02005', '15/05/2026', '31/05/2026', 95000, False, False),
        (306, 204, '01988', '01/03/2025', '14/03/2025', 18000, True, False),
    ]

    if produce_files:
        invoice_folder.mkdir(parents=True, exist_ok=True)
    for id_, resident_id, number, start, end, total, obsolete, matched in rows:
        Resident = resident.objects.get(id=resident_id)
        sub_items = pd.DataFrame({
            'Amount': [total / 100],
            'PaymentItemDates': [f'{start} - {end}'],
            'AdjustmentLabel': [''],
        })
        filename = invoice_folder / f'{number} - {Resident.name}.docx'
        if produce_files:
            write_inovice(
                invoice_folder,
                '27 May 2026',
                Resident,
                sub_items,
                total,
                number,
                batch_number=4,
            )
        invoice.objects.create(
            id=id_,
            Resident_id=resident_id,
            filename=str(filename),
            invoice_number=number,
            batch_number=4,
            date='2026-05-27',
            year=2026,
            total=total,
            obsolete=obsolete,
            matched=matched,
        )

    older_folder = settings.MEDIA_INVOICES / '2025' / '9. 31 December 2025'
    if produce_files:
        older_folder.mkdir(parents=True, exist_ok=True)
    Resident = resident.objects.get(id=201)
    sub_items = pd.DataFrame({
        'Amount': [300],
        'PaymentItemDates': ['01/12/2025 - 31/12/2025'],
        'AdjustmentLabel': [''],
    })
    if produce_files:
        write_inovice(
            older_folder,
            '31 December 2025',
            Resident,
            sub_items,
            30000,
            '01950',
            batch_number=9,
        )
    older_filename = older_folder / '01950 - Mr Arthur Test.docx'
    invoice.objects.create(
        id=307,
        Resident_id=201,
        filename=str(older_filename),
        invoice_number='01950',
        batch_number=9,
        date='2025-12-31',
        year=2025,
        total=30000,
        obsolete=False,
        matched=True,
    )


def create_payments():
    rows = [
        (401, 201, '2026-05-29', 'FASTER PAYMENTS RECEIPT ARTHUR TEST', 45000, True, 'Santander'),
        (402, 203, '2026-05-10', 'CARLA PRIVATE MAY CARE', 60000, False, 'RBS'),
        (403, 203, '2026-05-24', 'CARLA PRIVATE BALANCE', 60000, False, 'RBS'),
        (404, 205, '2026-05-12', 'CASH PAYMENT EVA CASH', 10000, False, 'Cash'),
        (405, None, '2026-05-21', 'UNMATCHED TEST PAYMENT', 12345, False, 'Santander'),
        (406, 204, '2025-03-20', 'DEREK FORMER FINAL PAYMENT', 18000, True, 'Cheque'),
    ]

    for id_, resident_id, date, description, amount, matched, payment_type in rows:
        payment.objects.create(
            id=id_,
            Resident_id=resident_id,
            date=date,
            description=description,
            amount=amount,
            matched=matched,
            type=payment_type,
        )


def create_sefton_payments(produce_files):
    if produce_files:
        remittance_folder = settings.MEDIA_REMITTANCE / '2026'
        remittance_folder.mkdir(parents=True, exist_ok=True)

        pd.DataFrame([
            {
                'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
                'ReportContext': 'Payment Period from 01/05/2026 to 28/05/2026',
                'Person': 'Mr',
                'ClientName': 'Test, Arthur (DEV-SEFTON-001)',
                'IsIncome': 1,
                'Amount': 450.00,
                'PaymentItemDates': '01/05/2026 - 28/05/2026',
                'AdjustmentLabel': '',
            },
            {
                'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
                'ReportContext': 'Payment Period from 01/05/2026 to 28/05/2026',
                'Person': 'Mr',
                'ClientName': 'Test, Arthur (DEV-SEFTON-001)',
                'IsIncome': 0,
                'Amount': 760.00,
                'PaymentItemDates': '01/05/2026 - 28/05/2026',
                'AdjustmentLabel': '',
            },
            {
                'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
                'ReportContext': 'Payment Period from 01/05/2026 to 28/05/2026',
                'Person': 'Ms',
                'ClientName': 'Noemail, Bella (DEV-SEFTON-002)',
                'IsIncome': 1,
                'Amount': 375.00,
                'PaymentItemDates': '01/05/2026 - 28/05/2026',
                'AdjustmentLabel': '',
            },
            {
                'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
                'ReportContext': 'Payment Period from 01/05/2026 to 28/05/2026',
                'Person': 'Ms',
                'ClientName': 'Noemail, Bella (DEV-SEFTON-002)',
                'IsIncome': 0,
                'Amount': 830.00,
                'PaymentItemDates': '01/05/2026 - 28/05/2026',
                'AdjustmentLabel': '',
            },
            {
                'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
                'ReportContext': 'Payment Period from 01/05/2026 to 28/05/2026',
                'Person': 'Miss',
                'ClientName': 'Cash, Eva (DEV-SEFTON-005)',
                'IsIncome': 1,
                'Amount': 215.50,
                'PaymentItemDates': '01/05/2026 - 14/05/2026',
                'AdjustmentLabel': '',
            },
            {
                'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
                'ReportContext': 'Payment Period from 01/05/2026 to 28/05/2026',
                'Person': 'Miss',
                'ClientName': 'Cash, Eva (DEV-SEFTON-005)',
                'IsIncome': 0,
                'Amount': 620.00,
                'PaymentItemDates': '01/05/2026 - 28/05/2026',
                'AdjustmentLabel': '',
            },
        ]).to_csv(remittance_folder / '4. 01 May - 28 May.csv', index=False)

    rows = [
        (501, 201, 4, '2026-05-28', 2026, 76000),
        (502, 202, 4, '2026-05-28', 2026, 83000),
        (503, 205, 4, '2026-05-28', 2026, 62000),
    ]

    for id_, resident_id, batch_number, date, year, total in rows:
        sefton_payment.objects.create(
            id=id_,
            Resident_id=resident_id,
            batch_number=batch_number,
            date=date,
            year=year,
            total=total,
        )


def create_sefton_action_items():
    sefton_action_item.objects.create(
        action_id='DEV-ACTION-001',
        title='Dummy funding query',
        relates_to='Mr Arthur Test',
        last_post_at=parse_datetime('2026-05-20T10:30:00+01:00'),
        conversation=[
            {
                'sender': 'Sefton Council',
                'sent_at': '2026-05-20T09:15:00+01:00',
                'message': 'Please confirm the care dates for the May invoice.',
            },
            {
                'sender': 'Orchard Lodge',
                'sent_at': '2026-05-20T10:30:00+01:00',
                'message': 'Care dates confirmed as 01/05/2026 to 28/05/2026.',
            },
        ],
    )


def create_dummy_login_details():
    sefton_login_details.objects.create(
        email='sefton-login@example.com',
        password='dummy-password',
        passcode='000000',
    )


def create_dev_user():
    User = get_user_model()
    User.objects.create_superuser(
        username=DEV_USERNAME,
        email='dev@example.com',
        password=DEV_PASSWORD,
        first_name='Orchard',
        last_name='Developer',
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create development database and optional development files.')
    parser.add_argument('--produce-files', action='store_true', help='Generate dummy media and secret files as well as database rows.')
    args = parser.parse_args()
    main(produce_files=args.produce_files)

import datetime

import pandas as pd

from django.test import SimpleTestCase, TestCase

from backend.payments import (
    combine_with_local_excel_file,
    match_payments_to_resident,
    normalize_payment_filters,
)
from main.models import payment, resident


class SantanderFileMergeTests(SimpleTestCase):
    def test_replaces_local_rows_from_download_start_date(self):
        local_payments = pd.DataFrame([
            {
                'Date': '08/07/2026',
                'Description': 'STALE TRANSACTION',
                'Money in': '£ 10.00',
                'Money Out': None,
                'Balance': '£ 110.00',
            },
            {
                'Date': '07/07/2026',
                'Description': 'OLDER TRANSACTION',
                'Money in': '£ 100.00',
                'Money Out': None,
                'Balance': '£ 100.00',
            },
        ])
        downloaded_payments = pd.DataFrame([
            {
                'Date': '08/07/2026',
                'Description': 'REPLACEMENT TRANSACTION',
                'Money in': '£ 20.00',
                'Money Out': None,
                'Balance': '£ 120.00',
            },
        ])

        combined_payments = combine_with_local_excel_file(
            local_payments,
            downloaded_payments,
            datetime.date(2026, 7, 8),
        )

        expected_payments = pd.concat(
            [downloaded_payments, local_payments.iloc[[1]]],
            ignore_index=True,
        )
        pd.testing.assert_frame_equal(combined_payments, expected_payments)


class PaymentFilterTests(TestCase):
    def test_normalize_payment_filters_treats_none_as_empty(self):
        self.assertEqual(normalize_payment_filters(None), [])

    def test_normalize_payment_filters_splits_semicolon_separated_filters(self):
        self.assertEqual(
            normalize_payment_filters(' Alice Smith ;   BOB JONES;  '),
            ['Alice Smith', 'BOB JONES'],
        )

    def test_filter_matches_unmatched_payment_to_resident(self):
        res = resident.objects.create(title='Mr', first='Arthur', last='Test')
        payment_ = payment.objects.create(
            date=datetime.date(2026, 6, 1),
            description='FASTER PAYMENTS RECEIPT ARTHUR TEST',
            amount=12345,
            type=payment.santander,
        )

        match_payments_to_resident(res.id, 'ARTHUR TEST', res.name, verbose=False)

        payment_.refresh_from_db()
        self.assertEqual(payment_.Resident, res)

    def test_filter_raises_if_matching_payment_belongs_to_another_resident(self):
        existing_resident = resident.objects.create(title='Mrs', first='Bella', last='Existing')
        new_resident = resident.objects.create(title='Mr', first='Charlie', last='New')
        payment_ = payment.objects.create(
            Resident=existing_resident,
            date=datetime.date(2026, 6, 1),
            description='FASTER PAYMENTS RECEIPT BELLA EXISTING',
            amount=12345,
            type=payment.santander,
        )

        with self.assertRaises(ValueError):
            match_payments_to_resident(new_resident.id, 'BELLA EXISTING', new_resident.name, verbose=False)

        payment_.refresh_from_db()
        self.assertEqual(payment_.Resident, existing_resident)

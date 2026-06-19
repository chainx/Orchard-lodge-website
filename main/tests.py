import datetime

from django.test import TestCase

from backend.payments import match_payments_to_resident, normalize_payment_filters
from main.models import payment, resident


class PaymentFilterTests(TestCase):
    def test_normalize_payment_filters_treats_none_as_empty(self):
        self.assertEqual(normalize_payment_filters(None), [])

    def test_normalize_payment_filters_splits_semicolon_separated_filters(self):
        self.assertEqual(
            normalize_payment_filters(' Alice Smith ; BOB JONES;  '),
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

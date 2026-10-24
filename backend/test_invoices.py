import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase, TestCase

from backend.invoices import (
    get_invoice_data_from_sefton_csv,
    get_or_add_resident,
    get_residents_with_similar_name,
    read_and_format_sefton_csv,
)
from main.models import invoice, resident, sefton_payment


class ReadAndFormatSeftonCSVTests(SimpleTestCase):
    """Test read_and_format_sefton_csv() validation and formatting.

    Also check validation order and invoice calculations through
    get_invoice_data_from_sefton_csv(), with resident lookup mocked.
    """

    def setUp(self):
        # Synthetic values only; the structure matches the historical exports.
        self.row = {
            'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
            'ReportContext': 'For Contract: Payment Period from 01/05/2026 to 28/05/2026',
            'Person': 'Mrs Alice Example',
            'ClientName': 'Example, Alice (001234)',
            'Amount': '25.50',
            'IsIncome': '1',
            'PaymentItemDates': '01/05/26 to 28/05/26',
            'AdjustmentLabel': '',
        }
        # Interleaved residents, split periods, credits, a cancelled contribution,
        # and an unrelated service reproduce patterns in the historical exports.
        def item(client, amount, income, dates='01/05/26 to 14/05/26', adjustment=''):
            title, first, last, sefton_id = client
            return {
                **self.row,
                'Person': f'{title} {first} {last}',
                'ClientName': f'{last}, {first} ({sefton_id})',
                'Amount': amount,
                'IsIncome': income,
                'PaymentItemDates': dates,
                'AdjustmentLabel': adjustment,
                'OriginInfo': 'Manual' if adjustment else 'Scheduled',
                'ServiceLevel': 'Residential',
                'Reason': 'Rate correction' if adjustment else 'Regular payment',
            }

        alice = ('Mrs', 'Alice', 'Example', '001234')
        bob = ('Mr', 'Bob', 'Sample', '005678')
        clara = ('Miss', 'Clara', 'Test', '009999')
        later = '15/05/26 to 28/05/26'
        self.rows = [
            item(alice, '25.50', '1'),
            item(bob, '40', '1'),
            item(alice, '100', '0'),
            item(clara, '15', '1'),
            item(bob, '120', '0'),
            item(alice, '12.75', '1', dates=later),
            {**item(alice, 'not money', '0'), 'ServiceTotalLabel': 'Another service'},
            item(alice, '-2.25', '1', adjustment='MA'),
            item(bob, '-10', '1', adjustment='MA'),
            item(alice, '50', '0', dates=later),
            item(clara, '-15', '1', adjustment='MA'),
            item(bob, '60', '0', dates=later),
            item(alice, '-5', '0', adjustment='MA'),
            item(clara, '90', '0'),
        ]

    def csv(self, rows=None):
        return StringIO(pd.DataFrame(rows if rows is not None else [self.row]).to_csv(index=False))

    def assert_invalid(self, source, message):
        # Validation must precede database lookups, resident saves and mkdir.
        with patch('backend.invoices.invoice.objects.filter') as lookup, \
                patch('backend.invoices.get_or_add_resident') as get_resident, \
                patch('backend.invoices.os.makedirs') as makedirs:
            with self.assertRaisesRegex(ValueError, message):
                get_invoice_data_from_sefton_csv(source)
            lookup.assert_not_called()
            get_resident.assert_not_called()
            makedirs.assert_not_called()

    def compile_rows(self, rows):
        with TemporaryDirectory() as directory:
            path = Path(directory) / '1. remittance.csv'
            path.write_text(self.csv(rows).getvalue())
            with patch('backend.invoices.invoice.objects.filter') as lookup, \
                    patch('backend.invoices.get_or_add_resident') as get_resident, \
                    patch('backend.invoices.compile_invoices_for_private_residents', return_value=[]), \
                    patch('backend.invoices.os.makedirs'):
                lookup.return_value.values_list.return_value = ['01000']
                get_resident.side_effect = lambda name, sefton_id, **kwargs: SimpleNamespace(
                    name=name, sefton_id=sefton_id,
                )
                return get_invoice_data_from_sefton_csv(path)

    def test_missing_required_columns(self):
        for column in self.row:
            with self.subTest(column=column):
                row = self.row.copy()
                del row[column]
                self.assert_invalid(self.csv([row]), f'missing required columns: {column}')

    def test_rejects_duplicate_column_headers(self):
        # Construct the source directly: a DataFrame cannot represent two
        # conflicting fields through the dictionaries used by csv().
        for column, value in (
            ('Amount', '999.99'),
            ('ClientName', '"Different, Resident (009876)"'),
        ):
            with self.subTest(column=column):
                source = (
                    'ServiceTotalLabel,ReportContext,Person,ClientName,Amount,'
                    f'IsIncome,PaymentItemDates,AdjustmentLabel,{column}\n'
                    'Total for Orchard Lodge Care Home,'
                    'For Contract: Payment Period from 01/05/2026 to 28/05/2026,'
                    'Mrs Alice Example,"Example, Alice (001234)",25.50,1,'
                    f'01/05/26 to 28/05/26,,{value}\n'
                )
                self.assert_invalid(StringIO(source), f'duplicate column names: {column}')

    def test_rejects_duplicate_column_headers_in_latin1_file(self):
        source = (
            'ServiceTotalLabel,ReportContext,Person,ClientName,Amount,'
            'IsIncome,PaymentItemDates,AdjustmentLabel,Amount\n'
            'Total for Orchard Lodge Care Home,'
            'For Contract: Payment Period from 01/05/2026 to 28/05/2026,'
            'Mrs Alice Example,"Example, Alice (001234)",25.50,1,'
            '01/05/26 to 28/05/26,Adjustment £1,999.99\n'
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / '1. remittance.csv'
            path.write_text(source, encoding='ISO-8859-1')
            self.assert_invalid(path, 'duplicate column names: Amount')

    def test_invalid_numeric_values(self):
        for column, values in {
            'Amount': ['', 'not money', 'NaN', 'inf', '-inf', '£25.50'],
            'IsIncome': ['', 'income', 'True', '2', '-1', '0.5', 'NaN', 'inf'],
        }.items():
            for value in values:
                with self.subTest(column=column, value=value):
                    self.assert_invalid(
                        self.csv([{**self.row, column: value}]),
                        rf'{column} must be .*CSV rows 2',
                    )

    def test_required_text_cannot_be_blank(self):
        for column in ('ServiceTotalLabel', 'ReportContext', 'Person', 'ClientName', 'PaymentItemDates'):
            with self.subTest(column=column):
                self.assert_invalid(self.csv([{**self.row, column: ' '}]), f'{column} must be non-empty text')

    def test_malformed_client_name(self):
        for value in (
            'Example, Alice', 'Example (001234)', 'Example, Alice ()',
            'Example, Alice (001234', 'Example,Alice (001234)',
            'Example,  (001234)', ' , Alice (001234)',
            ',, Alice (001234)', '(Example, Alice (001234)',
            ')Example, Alice (001234)', 'Example, ,Alice (001234)',
            'Example, (Alice (001234)', 'Example, )Alice (001234)',
        ):
            with self.subTest(value=value):
                self.assert_invalid(self.csv([{**self.row, 'ClientName': value}]), 'ClientName must be in the format')

    def test_invalid_payment_period(self):
        for value in (
            'No payment period',
            'Payment Period from 31/02/2026 to 28/05/2026',
            'Payment Period from 28/05/2026 to 01/05/2026',
        ):
            with self.subTest(value=value):
                self.assert_invalid(self.csv([{**self.row, 'ReportContext': value}]), 'ReportContext must be a valid')

    def test_inconsistent_payment_periods(self):
        second = {**self.row, 'ReportContext': 'Payment Period from 29/05/2026 to 25/06/2026'}
        self.assert_invalid(self.csv([self.row, second]), 'inconsistent payment periods')

    def test_invalid_payment_item_dates(self):
        for value in (
            'not a date', '01/05/26',
            '31/02/26 to 28/05/26', '01/05/26 to 31/05/invalid',
            '29/02/25 to 01/03/25', '01/05/26 to 31/06/26',
            '28/05/26 to 01/05/26', '31/12/26 to 01/01/26',
            '31/02/2026 - 28/05/2026', '28/05/2026 - 01/05/2026',
        ):
            with self.subTest(value=value):
                self.assert_invalid(
                    self.csv([{**self.row, 'PaymentItemDates': value}]),
                    r'PaymentItemDates must be a valid .*CSV rows 2',
                )

    def test_payment_item_dates_allow_supported_formats_and_historical_adjustments(self):
        dates = [
            '01/05/26 to 14/05/26',
            '15/05/2026 - 28/05/2026',
            '01/05/2026 to 14/05/2026',
            '15/05/26 - 28/05/26',
            # Adjustments can refer to periods outside the report's May 2026 range.
            '29/02/24 to 29/02/24',
            '01/06/2026 - 14/06/2026',
        ]
        rows = [
            {**self.row, 'PaymentItemDates': value, 'AdjustmentLabel': 'MA'}
            for value in dates
        ]
        df, period = read_and_format_sefton_csv(self.csv(rows))
        self.assertEqual(period, '01/05/2026 to 28/05/2026')
        self.assertEqual(df['PaymentItemDates'].tolist(), dates)
        self.assertEqual(df['Amount'].sum(), 153)

    def test_empty_or_wrong_service_csv(self):
        self.assert_invalid(StringIO(''), 'Invalid Sefton CSV')
        self.assert_invalid(StringIO(','.join(self.row) + '\n'), 'no data rows')
        self.assert_invalid(self.csv([{**self.row, 'ServiceTotalLabel': 'Another service'}]), 'no rows for Orchard Lodge')

    def test_malformed_csv(self):
        source = self.csv().getvalue()
        self.assert_invalid(StringIO(source + '"unterminated'), 'Invalid Sefton CSV')
        lines = source.splitlines()
        self.assert_invalid(StringIO(lines[0] + '\n' + lines[1] + ',extra\n'), 'more fields than the header')

    def test_formats_valid_rows_and_preserves_adjustments(self):
        rows = [
            self.row,
            {**self.row, 'Amount': '-2.50', 'IsIncome': '0', 'AdjustmentLabel': 'NA'},
            {**self.row, 'Amount': '0', 'AdjustmentLabel': 'MA'},
            {**self.row, 'ServiceTotalLabel': 'Another service', 'Amount': ''},
        ]
        df, period = read_and_format_sefton_csv(self.csv(rows))
        self.assertEqual(period, '01/05/2026 to 28/05/2026')
        self.assertEqual(df['Amount'].tolist(), [25.5, -2.5, 0])
        self.assertEqual(df['IsIncome'].tolist(), [1, 0, 1])
        self.assertEqual(df['AdjustmentLabel'].tolist(), ['', 'NA', 'MA'])
        self.assertEqual(df['Sefton ID'].tolist(), ['001234'] * 3)
        self.assertEqual(df['FormattedName'].tolist(), ['Mrs, Alice, Example'] * 3)

    def test_formats_titled_and_untitled_residents_with_multiword_names(self):
        names = [
            ('Alice Example', 'Alice', 'Example', ', Alice, Example'),
            ('Mrs Beth Sample', 'Beth', 'Sample', 'Mrs, Beth, Sample'),
            ('Dr Clara Jane van Test', 'Clara Jane', 'van Test', 'Dr, Clara Jane, van Test'),
            ('Dora Anne de Example', 'Dora Anne', 'de Example', ', Dora Anne, de Example'),
            ("Ms Élodie O'Example", 'Élodie', "O'Example", "Ms, Élodie, O'Example"),
        ]
        rows = [
            {
                **self.row,
                'Person': person,
                'ClientName': f'{last}, {first} ({index:06d})',
            }
            for index, (person, first, last, _) in enumerate(names, start=1)
        ]
        df, _ = read_and_format_sefton_csv(self.csv(rows))
        self.assertEqual(df['FormattedName'].tolist(), [expected for *_, expected in names])
        self.assertEqual(df['Sefton ID'].tolist(), ['000001', '000002', '000003', '000004', '000005'])

    def test_error_row_number_survives_service_filter(self):
        rows = [
            {**self.row, 'ServiceTotalLabel': 'Another service'},
            {**self.row, 'Amount': 'bad'},
        ]
        self.assert_invalid(self.csv(rows), r'Amount must be .*CSV rows 3')

    def test_latin1_encoding_fallback(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / '1. remittance.csv'
            path.write_text(self.csv([{**self.row, 'AdjustmentLabel': 'Adjustment £1'}]).getvalue(), encoding='ISO-8859-1')
            df, _ = read_and_format_sefton_csv(path)
        self.assertEqual(df.iloc[0]['AdjustmentLabel'], 'Adjustment £1')

    def test_interleaved_residents_adjustments_and_cancellations(self):
        for rows in (self.rows, self.rows[::-1]):
            with self.subTest(reversed=rows is not self.rows):
                invoices, payments, batch, _ = self.compile_rows(rows)
                invoices_by_id = {entry['Resident'].sefton_id: entry for entry in invoices}
                self.assertEqual(len(invoices), 2)
                # Alice: 25.50 + 12.75 - 2.25; Bob: 40 - 10.
                self.assertEqual(
                    {key: entry['total'] for key, entry in invoices_by_id.items()},
                    {'001234': 3600, '005678': 3000},
                )
                self.assertEqual(len(payments), 3)
                # Costs less personal contributions; Clara's +15/-15 cancels.
                self.assertEqual(
                    {entry['Resident'].sefton_id: entry['total'] for entry in payments},
                    {'001234': 10900, '005678': 15000, '009999': 9000},
                )
                self.assertCountEqual(
                    invoices_by_id['001234']['sub_items']['Amount'].tolist(),
                    [25.50, 12.75, -2.25],
                )
                self.assertEqual({entry['invoice_number'] for entry in invoices}, {'01001', '01002'})
                self.assertEqual(batch, 1)

    def test_rejects_adjacent_and_nonadjacent_duplicate_source_rows(self):
        for original in (0, 2):  # Duplicate either a contribution or a council cost.
            for position in (original + 1, len(self.rows)):
                with self.subTest(original=original, duplicate_position=position):
                    rows = [row.copy() for row in self.rows]
                    rows.insert(position, rows[original].copy())
                    self.assert_invalid(
                        self.csv(rows),
                        rf'duplicate rows .*CSV rows {original + 2}, {position + 2}',
                    )

    def test_matching_invoice_fields_with_distinct_source_metadata_are_preserved(self):
        # Real 2020 exports repeat invoice fields but differ in these columns.
        base = {**self.row, 'OriginInfo': 'Scheduled', 'ServiceLevel': 'Residential', 'Reason': 'Regular'}
        for column, value in (
            ('OriginInfo', 'Manual'), ('ServiceLevel', 'Nursing'), ('Reason', 'Correction'),
        ):
            with self.subTest(column=column):
                rows = [base, {**base, column: value}, {**base, 'Amount': '100', 'IsIncome': '0'}]
                invoices, payments, _, _ = self.compile_rows(rows)
                self.assertEqual(len(invoices[0]['sub_items']), 2)
                self.assertEqual(invoices[0]['total'], 5100)
                self.assertEqual(payments[0]['total'], 4900)

    def test_same_amounts_in_distinct_periods_are_preserved(self):
        rows = [self.row, {**self.row, 'PaymentItemDates': '15/05/26 to 28/05/26'}]
        invoices, _, _, _ = self.compile_rows(rows)
        self.assertEqual(invoices[0]['total'], 5100)
        self.assertEqual(len(invoices[0]['sub_items']), 2)

    def test_same_id_with_conflicting_names_is_rejected(self):
        for changes in (
            {'Person': 'Mr Alice Example'},
            {'Person': 'Mrs Alicia Example', 'ClientName': 'Example, Alicia (001234)'},
        ):
            with self.subTest(changes=changes):
                rows = [*self.rows, {**self.rows[0], **changes, 'Amount': '10'}]
                self.assert_invalid(self.csv(rows), 'Sefton ID must be associated with a single resident name')

    def test_invalid_cells_later_in_multi_resident_csv(self):
        for column, value in (
            ('Amount', 'bad'), ('IsIncome', '2'), ('ClientName', 'malformed'),
            ('Person', ' '), ('PaymentItemDates', ''), ('ReportContext', 'missing dates'),
            ('ClientName', ',, Alice (001234)'),
            ('ClientName', 'Example, (Alice (001234)'),
            ('PaymentItemDates', '31/02/26 to 28/05/26'),
            ('PaymentItemDates', '28/05/2026 - 01/05/2026'),
        ):
            with self.subTest(column=column):
                rows = [row.copy() for row in self.rows]
                for position in (9, 13):
                    rows[position][column] = value
                self.assert_invalid(self.csv(rows), rf'{column} must be .*CSV rows 11, 15')

    def test_different_payment_period_at_end_of_multi_resident_csv(self):
        rows = [row.copy() for row in self.rows]
        rows[-1]['ReportContext'] = 'Payment Period from 29/05/2026 to 25/06/2026'
        self.assert_invalid(self.csv(rows), 'inconsistent payment periods')

    def test_duplicate_rows_in_excluded_service_do_not_affect_totals(self):
        rows = [*self.rows, self.rows[6].copy()]
        invoices, payments, _, _ = self.compile_rows(rows)
        self.assertEqual(sum(entry['total'] for entry in invoices), 6600)
        self.assertEqual(sum(entry['total'] for entry in payments), 34900)


class GetOrAddResidentTests(TestCase):
    """Test get_or_add_resident() using Django's test database.

    Exercise resident matching directly and through
    get_invoice_data_from_sefton_csv(), including allocation of invoice and
    payment amounts. Also cover get_residents_with_similar_name().
    These tests do not exercise saving generated invoices or payments.
    """

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        # Importing currently requires a previous invoice to allocate its number.
        invoice.objects.create(invoice_number='01000')
        self.rows = [
            self.row('001234', '25.50', '1'),
            self.row('005678', '40.00', '1'),
            self.row('001234', '100.00', '0'),
            self.row('005678', '150.00', '0'),
        ]

    def row(self, sefton_id, amount, income):
        return {
            'ServiceTotalLabel': 'Total for Orchard Lodge Care Home',
            'ReportContext': 'For Contract: Payment Period from 01/05/2026 to 28/05/2026',
            'Person': 'Mrs Alice Example',
            'ClientName': f'Example, Alice ({sefton_id})',
            'Amount': amount,
            'IsIncome': income,
            'PaymentItemDates': '01/05/26 to 28/05/26',
            'AdjustmentLabel': '',
        }

    def import_rows(self, rows=None, save=True):
        rows = self.rows if rows is None else rows
        path = Path(self.directory.name) / '1. remittance.csv'
        with path.open('w', newline='', encoding='utf-8') as source:
            writer = csv.DictWriter(source, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        with self.settings(MEDIA_INVOICES=Path(self.directory.name) / 'invoices'):
            result = get_invoice_data_from_sefton_csv(path, save_new_residents=save)
        # This function prepares billing; it must not persist the resulting bills.
        self.assertEqual(invoice.objects.count(), 1)
        self.assertEqual(sefton_payment.objects.count(), 0)
        return result

    def assert_separate_billing(self, result):
        invoices, payments, batch, _ = result
        self.assertEqual(batch, 1)
        self.assertEqual(len(invoices), 2)
        self.assertEqual(len(payments), 2)
        self.assertEqual(len({entry['Resident'].pk for entry in invoices}), 2)
        self.assertEqual(
            {entry['Resident'].sefton_id: entry['total'] for entry in invoices},
            {'001234': 2550, '005678': 4000},
        )
        self.assertEqual(
            {entry['Resident'].sefton_id: entry['total'] for entry in payments},
            {'001234': 7450, '005678': 11000},
        )

    def test_same_names_with_different_ids_create_distinct_residents_and_bills(self):
        self.assert_separate_billing(self.import_rows())
        self.assertCountEqual(
            resident.objects.values_list('sefton_id', flat=True), ['001234', '005678'],
        )
        self.assertEqual({res.name for res in resident.objects.all()}, {'Mrs Alice Example'})

    def test_existing_ids_take_precedence_over_ambiguous_matching_names(self):
        existing = {
            sefton_id: resident.objects.create(
                title='Mrs', first='Alice', last='Example', sefton_id=sefton_id,
            )
            for sefton_id in ('001234', '005678')
        }
        resident.objects.create(title='Mrs', first='Alice', last='Example', sefton_id=None)
        result = self.import_rows(list(reversed(self.rows)))
        self.assert_separate_billing(result)
        for entry in result[0]:
            res = entry['Resident']
            self.assertEqual(res.pk, existing[res.sefton_id].pk)
        self.assertEqual(resident.objects.count(), 3)

    def test_name_matching_ignores_different_ids_before_checking_ambiguity(self):
        for missing_id in (None, ''):
            with self.subTest(missing_id=missing_id):
                resident.objects.all().delete()
                assigned = resident.objects.create(
                    title='Mrs', first='Alice', last='Example', sefton_id='001234',
                )
                unassigned = resident.objects.create(
                    title='Mrs', first='Alice', last='Example', sefton_id=missing_id,
                )
                result = self.import_rows()
                self.assert_separate_billing(result)
                assigned.refresh_from_db()
                unassigned.refresh_from_db()
                self.assertEqual(assigned.sefton_id, '001234')
                self.assertEqual(unassigned.sefton_id, '005678')
                self.assertEqual(resident.objects.count(), 2)
                self.assertEqual(result[0][1]['Resident'].pk, unassigned.pk)

    def test_preview_does_not_save_id_onto_existing_resident(self):
        for missing_id in (None, ''):
            with self.subTest(missing_id=missing_id):
                resident.objects.all().delete()
                existing = resident.objects.create(
                    title='Mrs', first='Alice', last='Example', sefton_id=missing_id,
                )
                invoices, _, _, _ = self.import_rows([self.rows[0]], save=False)
                self.assertEqual(invoices[0]['Resident'].pk, existing.pk)
                self.assertEqual(invoices[0]['Resident'].sefton_id, '001234')
                self.assertEqual(invoices[0]['total'], 2550)
                existing.refresh_from_db()
                self.assertEqual(existing.sefton_id, missing_id)
                self.assertEqual(resident.objects.count(), 1)

    def test_preview_does_not_save_new_residents(self):
        invoices, payments, _, _ = self.import_rows(save=False)
        self.assertEqual(resident.objects.count(), 0)
        self.assertEqual([entry['total'] for entry in invoices], [2550, 4000])
        self.assertEqual([entry['total'] for entry in payments], [7450, 11000])
        self.assertTrue(all(entry['Resident'].pk is None for entry in invoices))

    def test_preview_reserves_idless_resident_for_only_one_source_id(self):
        for missing_id in (None, ''):
            with self.subTest(missing_id=missing_id):
                resident.objects.all().delete()
                existing = resident.objects.create(
                    title='Mrs', first='Alice', last='Example', sefton_id=missing_id,
                )
                result = self.import_rows(save=False)
                self.assert_separate_billing(result)
                invoices, payments, _, _ = result
                for entries in (invoices, payments):
                    self.assertEqual(entries[0]['Resident'].pk, existing.pk)
                    self.assertIsNone(entries[1]['Resident'].pk)
                existing.refresh_from_db()
                self.assertEqual(existing.sefton_id, missing_id)
                self.assertEqual(resident.objects.count(), 1)

    def test_exact_id_match_takes_precedence_over_preview_name_exclusions(self):
        existing = resident.objects.create(
            title='Mrs', first='Alice', last='Example', sefton_id='001234',
        )
        matched = get_or_add_resident(
            'Mrs, Alice, Example', '001234', save=False,
            excluded_resident_ids={existing.pk},
        )
        self.assertEqual(matched, existing)
        self.assertEqual(resident.objects.count(), 1)

    def test_person_without_title_creates_correct_resident(self):
        row = {**self.rows[0], 'Person': 'Alice Example'}
        invoices, _, _, _ = self.import_rows([row])
        res = resident.objects.get(sefton_id='001234')
        self.assertEqual((res.title, res.first, res.last), ('', 'Alice', 'Example'))
        self.assertEqual(res.name, 'Alice Example')
        self.assertEqual(invoices[0]['Resident'], res)
        self.assertEqual(invoices[0]['total'], 2550)

    def test_ambiguous_unassigned_names_are_rejected_without_assigning_an_id(self):
        for missing_id in (None, ''):
            resident.objects.create(title='Mrs', first='Alice', last='Example', sefton_id=missing_id)
        with self.assertRaisesRegex(ValueError, 'Multiple close matches'):
            self.import_rows([self.rows[0]])
        self.assertCountEqual(resident.objects.values_list('sefton_id', flat=True), [None, ''])

    def test_duplicate_exact_ids_are_not_hidden_by_name_fallback(self):
        resident.objects.create(title='Mrs', first='Alice', last='Example', sefton_id='001234')
        resident.objects.create(title='Mr', first='Bob', last='Sample', sefton_id='001234')
        with self.assertRaises(resident.MultipleObjectsReturned):
            self.import_rows([self.rows[0]])
        self.assertEqual(resident.objects.count(), 2)

    def test_missing_id_does_not_match_an_unrelated_resident_with_missing_id(self):
        for missing_id in (None, ''):
            with self.subTest(missing_id=missing_id):
                resident.objects.all().delete()
                unrelated = resident.objects.create(
                    title='Mr', first='Bob', last='Sample', sefton_id=missing_id,
                )
                res = get_or_add_resident('Mrs, Alice, Example', sefton_id=missing_id)
                self.assertNotEqual(res.pk, unrelated.pk)
                self.assertEqual(res.name, 'Mrs Alice Example')
                self.assertEqual(resident.objects.count(), 2)

    def test_name_lookup_without_id_restriction_still_finds_assigned_resident(self):
        existing = resident.objects.create(
            title='Mrs', first='Alice', last='Example', sefton_id='001234',
        )
        self.assertEqual(get_residents_with_similar_name('Alice', 'Example', False), existing)

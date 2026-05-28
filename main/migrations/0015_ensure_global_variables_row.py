import datetime
from django.db import migrations


def ensure_global_variables_row(apps, schema_editor):
    global_variables = apps.get_model('main', 'global_variables')
    global_variables.objects.get_or_create(
        pk=1,
        defaults={
            'payments_invoices_cutoff_date': datetime.date(2023, 3, 1),
            'recently_left_cutoff_date': datetime.date(2025, 2, 1),
            'unmatched_payment_cutoff_date': datetime.date(2025, 4, 1),
            'statement_cover_letter_thresholds': {
                'lower': 0,
                'upper': 1e8,
                'urgent_upper': 1e10,
            },
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0014_global_variables'),
    ]

    operations = [
        migrations.RunPython(ensure_global_variables_row, migrations.RunPython.noop),
    ]

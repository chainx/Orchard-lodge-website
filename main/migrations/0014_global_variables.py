import datetime
import main.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0013_resident_email_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='global_variables',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_bank_statement_downloaded_at', models.DateTimeField(blank=True, null=True)),
                ('last_remittance_advice_downloaded_at', models.DateTimeField(blank=True, null=True)),
                ('last_action_item_downloaded_at', models.DateTimeField(blank=True, null=True)),
                ('payments_invoices_cutoff_date', models.DateField(default=datetime.date(2023, 3, 1))),
                ('recently_left_cutoff_date', models.DateField(default=datetime.date(2025, 2, 1))),
                ('unmatched_payment_cutoff_date', models.DateField(default=datetime.date(2025, 4, 1))),
                ('statement_cover_letter_thresholds', models.JSONField(default=main.models.default_cover_letter_thresholds)),
            ],
        ),
    ]

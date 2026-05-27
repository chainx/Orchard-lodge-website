from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0012_resident_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='resident',
            name='email_name',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]

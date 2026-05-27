from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0011_sefton_payment'),
    ]

    operations = [
        migrations.AddField(
            model_name='resident',
            name='email',
            field=models.EmailField(blank=True, default='', max_length=256),
        ),
    ]

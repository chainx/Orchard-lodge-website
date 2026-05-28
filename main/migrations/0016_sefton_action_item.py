from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0015_ensure_global_variables_row'),
    ]

    operations = [
        migrations.CreateModel(
            name='sefton_action_item',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_id', models.CharField(max_length=64, unique=True)),
                ('title', models.CharField(max_length=256)),
                ('relates_to', models.CharField(blank=True, max_length=256)),
                ('conversation', models.JSONField(default=list)),
                ('downloaded_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]

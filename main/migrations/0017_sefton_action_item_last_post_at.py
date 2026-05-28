from django.db import migrations, models
from django.utils.dateparse import parse_datetime


def populate_last_post_at(apps, schema_editor):
    sefton_action_item = apps.get_model('main', 'sefton_action_item')
    for action_item in sefton_action_item.objects.all():
        sent_times = [
            parse_datetime(post['sent_at'])
            for post in action_item.conversation
            if post.get('sent_at')
        ]
        sent_times = [sent_at for sent_at in sent_times if sent_at is not None]
        if sent_times:
            action_item.last_post_at = max(sent_times)
            action_item.save(update_fields=['last_post_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0016_sefton_action_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='sefton_action_item',
            name='last_post_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(populate_last_post_at, migrations.RunPython.noop),
    ]

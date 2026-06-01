from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0012_backfill_dev_env_actor_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="developerenvironment",
            name="external_ui",
            field=models.URLField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="devpost_link",
            field=models.URLField(blank=True, max_length=512, null=True),
        ),
    ]

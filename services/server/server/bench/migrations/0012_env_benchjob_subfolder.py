from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0011_env_resubmission_and_truncated"),
    ]

    operations = [
        migrations.AddField(
            model_name="developerenvironment",
            name="subfolder",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="benchjob",
            name="subfolder",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0010_archive_smoke_cli_nav_test"),
    ]

    operations = [
        migrations.AlterField(
            model_name="episode",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("truncated", "Truncated"),
                    ("failed", "Failed"),
                    ("timeout", "Timeout"),
                ],
                db_index=True,
                default="pending",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="submission_version",
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="domain_history",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="resubmitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

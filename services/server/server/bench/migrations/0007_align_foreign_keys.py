# Align bench FK definitions with models (db_column / to_field on related_name paths)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0006_remove_run_environment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="benchjob",
            name="domain",
            field=models.ForeignKey(
                blank=True,
                db_column="domain_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bench_jobs",
                to="bench.domain",
            ),
        ),
        migrations.AlterField(
            model_name="benchjob",
            name="environment",
            field=models.ForeignKey(
                db_column="env_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bench_jobs",
                to="bench.developerenvironment",
            ),
        ),
        migrations.AlterField(
            model_name="developerenvironment",
            name="domain",
            field=models.ForeignKey(
                blank=True,
                db_column="domain_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="developer_environments",
                to="bench.domain",
            ),
        ),
        migrations.AlterField(
            model_name="environmentusage",
            name="domain",
            field=models.ForeignKey(
                db_column="domain_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="usage_records",
                to="bench.domain",
            ),
        ),
        migrations.AlterField(
            model_name="environmentusage",
            name="run",
            field=models.ForeignKey(
                db_column="run_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="usage_records",
                to="bench.run",
            ),
        ),
        migrations.AlterField(
            model_name="episode",
            name="run",
            field=models.ForeignKey(
                db_column="run_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="episodes",
                to="bench.run",
            ),
        ),
        migrations.AlterField(
            model_name="leaderboard",
            name="domain",
            field=models.ForeignKey(
                db_column="domain_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="leaderboard_entries",
                to="bench.domain",
            ),
        ),
        migrations.AlterField(
            model_name="leaderboard",
            name="run",
            field=models.OneToOneField(
                db_column="run_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="leaderboard_entry",
                to="bench.run",
            ),
        ),
        migrations.AlterField(
            model_name="run",
            name="domain",
            field=models.ForeignKey(
                db_column="domain_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="runs",
                to="bench.domain",
            ),
        ),
    ]

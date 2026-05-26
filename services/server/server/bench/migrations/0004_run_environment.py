# Run.environment FK links runs to developer environments

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0003_alter_benchguestsession_id_alter_benchjob_domain_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="environment",
            field=models.ForeignKey(
                blank=True,
                db_column="env_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="runs",
                to="bench.developerenvironment",
            ),
        ),
    ]

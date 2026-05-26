from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0004_run_environment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="run",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=64,
            ),
        ),
    ]

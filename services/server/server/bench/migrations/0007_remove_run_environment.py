from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0006_alter_run_status"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="run",
            name="environment",
        ),
    ]

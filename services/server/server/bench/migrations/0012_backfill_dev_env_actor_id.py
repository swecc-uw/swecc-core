from __future__ import annotations

from django.db import migrations
from django.db.models import Q


def backfill_dev_env_actor_id(apps, schema_editor):
    DeveloperEnvironment = apps.get_model("bench", "DeveloperEnvironment")
    legacy_actor = Q(actor_id__isnull=True) | Q(actor_id="")
    legacy_scope = Q(scope="solo") | Q(scope="") | Q(scope__isnull=True)
    for row in DeveloperEnvironment.objects.filter(legacy_actor, legacy_scope).exclude(owner_id=""):
        row.actor_id = row.owner_id
        if not row.scope:
            row.scope = "solo"
        if not row.actor_type:
            row.actor_type = "member"
        row.save(update_fields=["actor_id", "scope", "actor_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0011_env_resubmission_and_truncated"),
    ]

    operations = [
        migrations.RunPython(backfill_dev_env_actor_id, migrations.RunPython.noop),
    ]

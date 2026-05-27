"""One-time: remove legacy CLI smoke domain from the published gallery."""

from __future__ import annotations

from django.db import migrations


def archive_smoke_cli_nav_test(apps, schema_editor):
    Domain = apps.get_model("bench", "Domain")
    Run = apps.get_model("bench", "Run")
    try:
        row = Domain.objects.get(pk="smoke-cli-nav-test")
    except Domain.DoesNotExist:
        return
    data = row.data if isinstance(row.data, dict) else {}
    if data.get("status") != "archived":
        Domain.objects.filter(pk="smoke-cli-nav-test").update(
            data={**data, "status": "archived"},
            published=False,
        )
    Run.objects.filter(
        domain_id="smoke-cli-nav-test",
        visibility="gallery_public",
    ).update(visibility="private")


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0009_remove_cancelled_from_non_run_status"),
    ]

    operations = [
        migrations.RunPython(archive_smoke_cli_nav_test, migrations.RunPython.noop),
    ]

# Generated manually for bench auth + teams

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BenchGuestSession",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="BenchTeam",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("join_code", models.CharField(db_index=True, max_length=4, unique=True)),
                ("created_by_user_id", models.IntegerField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="BenchTeamMembership",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("user_id", models.IntegerField(db_index=True)),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Owner"), ("member", "Member")],
                        default="member",
                        max_length=16,
                    ),
                ),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="bench.benchteam",
                    ),
                ),
            ],
            options={
                "unique_together": {("team", "user_id")},
            },
        ),
        migrations.AddField(
            model_name="run",
            name="actor_type",
            field=models.CharField(
                blank=True,
                choices=[("guest", "Guest"), ("member", "Member")],
                db_index=True,
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="run",
            name="actor_id",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="run",
            name="visibility",
            field=models.CharField(
                choices=[("private", "Private"), ("gallery_public", "Gallery public")],
                db_index=True,
                default="private",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="run",
            name="expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="run",
            name="team",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="runs",
                to="bench.benchteam",
            ),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="scope",
            field=models.CharField(
                choices=[("solo", "Solo"), ("team", "Team")],
                db_index=True,
                default="solo",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="actor_type",
            field=models.CharField(
                blank=True,
                choices=[("guest", "Guest"), ("member", "Member")],
                db_index=True,
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="actor_id",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="created_by_user_id",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="developerenvironment",
            name="team",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="developer_environments",
                to="bench.benchteam",
            ),
        ),
    ]

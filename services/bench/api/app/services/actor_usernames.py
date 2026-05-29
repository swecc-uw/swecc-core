"""Resolve SWECC member usernames for bench run actors (members_user table)."""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import connection


@sync_to_async
def member_usernames_by_id(user_ids: list[int]) -> dict[str, str]:
    if not user_ids:
        return {}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, username FROM members_user WHERE id IN %s",
                [tuple(user_ids)],
            )
            return {str(row[0]): row[1] for row in cursor.fetchall()}
    except Exception:
        return {}

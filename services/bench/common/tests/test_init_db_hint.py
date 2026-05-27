from bench_common.storage.db_hints import init_db_hint


def test_init_db_hint_team_table_missing():
    exc = Exception('relation "bench_benchteam" does not exist')
    hint = init_db_hint(exc)
    assert "0002_auth_teams" in hint
    assert "team tables missing" in hint


def test_init_db_hint_generic_missing():
    exc = Exception("no such table: bench_domain")
    hint = init_db_hint(exc)
    assert "manage.py migrate" in hint

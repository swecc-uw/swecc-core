from __future__ import annotations

import argparse
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bench_common.cli import main as cli_main


def test_format_http_error_includes_json_detail():
    request = httpx.Request("POST", "https://api.swecc.org/bench/v1/teams")
    response = httpx.Response(
        500,
        request=request,
        json={"detail": "Internal server error"},
    )
    msg = cli_main._format_http_error(response)
    assert "500" in msg
    assert "Internal server error" in msg


def test_cmd_team_create_prints_api_detail_on_500(capsys: pytest.CaptureFixture[str]) -> None:
    request = httpx.Request("POST", "https://api.swecc.org/bench/v1/teams")
    response = httpx.Response(
        500,
        request=request,
        json={"detail": "Internal server error"},
    )
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("error", request=request, response=response)
    )
    session = MagicMock()
    session.client.post.return_value = response
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch.object(cli_main, "_require_member_session", return_value=session):
        with pytest.raises(SystemExit) as exc:
            cli_main._cmd_team_create(argparse.Namespace(name="hello"))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Internal server error" in err

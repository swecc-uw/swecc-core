import json

import pytest
from app.mq.producers import build_job_execute_body, build_run_execute_body


def test_build_run_execute_body():
    body = build_run_execute_body({"run_id": "run-abc"})
    assert json.loads(body.decode()) == {"run_id": "run-abc"}


def test_build_run_execute_body_requires_run_id():
    with pytest.raises(ValueError, match="run_id"):
        build_run_execute_body({})


def test_build_job_execute_body():
    body = build_job_execute_body({"job_id": "job-xyz"})
    assert json.loads(body.decode()) == {"job_id": "job-xyz"}


def test_build_job_execute_body_requires_job_id():
    with pytest.raises(ValueError, match="job_id"):
        build_job_execute_body({})

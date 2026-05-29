import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_consume_job_execute_decodes_body(monkeypatch):
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")

    with patch("app.mq.consumers._process_bench_job", new_callable=AsyncMock) as process_job:
        from app.mq.consumers import consume_job_execute

        body = json.dumps({"job_id": "job-1"}).encode()
        await consume_job_execute(body, None)
        import asyncio

        await asyncio.sleep(0.05)

    process_job.assert_awaited_once_with("job-1")

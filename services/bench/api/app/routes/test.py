import structlog
from app.auth.access import assert_run_read
from app.auth.deps import get_optional_principal, require_member
from app.auth.principal import Member
from app.auth.resolve import auth_disabled
from app.services.url_safety import assert_public_http_url
from bench.models import ActorType, Visibility
from bench_common.core.run import AgentConfig, Episode
from bench_common.orchestrator import service as orchestrator
from bench_common.storage import database as db
from bench_common.storage.trace_store import trace_store
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/test", tags=["test"])
log = structlog.get_logger()


class TestEpisodeRequest(BaseModel):
    domain_id: str
    binding_vow_version: str
    agent_config: AgentConfig
    env_url: str | None = None
    seed: int | None = None


@router.post("/episode", response_model=Episode, status_code=200)
async def start_test_episode(
    req: TestEpisodeRequest,
    member: Member = Depends(require_member),
) -> Episode:
    domain = await db.get_domain(req.domain_id)
    if domain is None:
        log.warning("test_episode_domain_missing", domain_id=req.domain_id)
        raise HTTPException(status_code=404, detail=f"Domain '{req.domain_id}' not found")
    if not auth_disabled() and domain.owner_id != str(member.user_id):
        log.warning(
            "test_episode_forbidden",
            domain_id=req.domain_id,
            owner_id=domain.owner_id,
            requester_id=member.user_id,
        )
        raise HTTPException(status_code=403, detail="Not allowed to test this domain")

    log.info(
        "test_episode_start",
        domain_id=req.domain_id,
        model=req.agent_config.model,
        seed=req.seed,
        has_env_url_override=req.env_url is not None,
        requester_id=member.user_id,
    )
    if not auth_disabled():
        assert_public_http_url(req.env_url, field="env_url")
    try:
        episode = await orchestrator.run_test_episode(
            domain_id=req.domain_id,
            binding_vow_version=req.binding_vow_version,
            agent_config=req.agent_config,
            env_url=req.env_url,
            seed=req.seed,
        )
    except ValueError as exc:
        log.warning("test_episode_rejected", domain_id=req.domain_id, detail=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    run = await db.get_run(episode.run_id)
    if run is not None:
        await db.save_run(
            run,
            actor_type=ActorType.MEMBER,
            actor_id=str(member.user_id),
            visibility=Visibility.PRIVATE,
        )
    log.info(
        "test_episode_complete",
        episode_id=episode.id,
        run_id=episode.run_id,
        status=episode.status,
        steps=episode.steps,
        requester_id=member.user_id,
    )
    return episode


@router.get("/episode/{episode_id}", response_model=Episode)
async def get_episode(
    episode_id: str,
    principal=Depends(get_optional_principal),
) -> Episode:
    episode = await db.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")
    await assert_run_read(episode.run_id, principal)
    return episode


@router.get("/episode/{episode_id}/trace")
async def get_episode_trace(
    episode_id: str,
    principal=Depends(get_optional_principal),
) -> list:
    episode = await db.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")
    await assert_run_read(episode.run_id, principal)
    events = await trace_store.read(episode_id)
    return [e.model_dump() for e in events]

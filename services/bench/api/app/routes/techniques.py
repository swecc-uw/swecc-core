from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/techniques", tags=["techniques"])

_TECHNIQUES = {
    "tool_calling": {
        "id": "tool_calling",
        "version": "1.0.0",
        "description": (
            "Injects tool/function definitions into the LLM prompt. "
            "The domain's technique config defines available tools as JSON Schema."
        ),
        "config_schema": {
            "type": "object",
            "properties": {
                "tools": {
                    "type": "array",
                    "description": "List of tool definitions (JSON Schema objects)",
                }
            },
        },
    },
    "memory": {
        "id": "memory",
        "version": "1.0.0",
        "description": (
            "Maintains a sliding window of recent (obs, action, reward) triples "
            "and injects a history summary into the agent prompt."
        ),
        "config_schema": {
            "type": "object",
            "properties": {
                "window_size": {
                    "type": "integer",
                    "default": 10,
                    "description": "Max number of steps to retain",
                },
                "summarize_after": {
                    "type": "integer",
                    "default": 5,
                    "description": "Summarize after this many steps",
                },
            },
        },
    },
    "multi_agent": {
        "id": "multi_agent",
        "version": "1.0.0",
        "description": (
            "Manages multiple named roles within a single episode, "
            "injecting the current role into the agent prompt."
        ),
        "config_schema": {
            "type": "object",
            "properties": {
                "roles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of agent role names",
                },
                "turn_order": {
                    "type": "string",
                    "enum": ["alternating", "sequential"],
                    "default": "alternating",
                },
            },
        },
    },
}


@router.get("", response_model=list[dict])
async def list_techniques() -> list[dict]:
    return list(_TECHNIQUES.values())


@router.get("/{technique_id}", response_model=dict)
async def get_technique(technique_id: str) -> dict:
    t = _TECHNIQUES.get(technique_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Technique '{technique_id}' not found")
    return t

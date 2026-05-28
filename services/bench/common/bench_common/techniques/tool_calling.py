"""
Tool schema injector technique.

Injects tool definitions from the domain's technique config into the system
prompt so the model knows what tools are available in the environment.

IMPORTANT — this technique does NOT dispatch tool calls.
Tool execution is the environment's responsibility:

    Your env's step() receives the model's tool call as a structured action
    (defined by your action_space), executes the tool, and returns the result
    as the next observation.  The platform never intercepts or routes tool calls
    — it only facilitates the model seeing the schema.

    Example action_space for a tool-calling env:

        action_space = SpaceSpec(
            type=SpaceType.JSON,
            schema_ref=json.dumps({
                "type": "object",
                "properties": {
                    "tool":  {"type": "string", "enum": ["search", "click", "type"]},
                    "args":  {"type": "object"},
                },
                "required": ["tool", "args"],
            }),
        )

    Then in step():
        tool = action["tool"]
        args = action["args"]
        result = self._execute_tool(tool, args)
        return StepResult(observation=result, ...)

The technique_id is "tool_calling" for backward compatibility with existing
domain binding vows.
"""

from __future__ import annotations

import json
from typing import Any

from bench_common.core.binding_vow import TechniqueDeclaration
from bench_common.techniques.base import Technique


class ToolSchemaInjectorTechnique(Technique):
    """Injects tool schema definitions into the agent's system prompt.

    Configure via TechniqueDeclaration config_schema::

        techniques:
          - technique_id: tool_calling
            config_schema:
              tools:
                - name: search
                  description: Search the web
                  parameters: { ... }

    The ``tools`` list is serialised as JSON and appended to the system prompt
    under an "Available Tools" heading.  Your env's step() is responsible for
    parsing the model's chosen tool call from the action and executing it.
    """

    def __init__(self) -> None:
        self._tools: list[dict[str, Any]] = []

    def id(self) -> str:
        return "tool_calling"

    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        return declaration.technique_id == self.id()

    async def on_episode_start(self, episode_id: str, config: dict[str, Any]) -> None:
        self._tools = config.get("tools", [])

    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._tools:
            return {}
        tools_text = json.dumps(self._tools, indent=2)
        return {"Available Tools": f"```json\n{tools_text}\n```"}

    async def after_action(
        self,
        action: Any,
        step_result: Any,
        agent_state: dict[str, Any],
    ) -> None:
        # Tool dispatch is the env's responsibility — nothing to do here.
        pass

    async def on_episode_end(self, episode_id: str, terminal_info: dict[str, Any]) -> None:
        self._tools = []


# Backward-compatible alias — existing code that imports ToolCallingTechnique
# by name continues to work.
ToolCallingTechnique = ToolSchemaInjectorTechnique

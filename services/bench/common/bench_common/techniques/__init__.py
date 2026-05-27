from bench_common.techniques.base import Technique
from bench_common.techniques.memory import EpisodicMemoryTechnique
from bench_common.techniques.multi_agent import MultiAgentTechnique
from bench_common.techniques.tool_calling import ToolCallingTechnique, ToolSchemaInjectorTechnique

TECHNIQUE_REGISTRY: dict[str, type[Technique]] = {
    "tool_calling": ToolSchemaInjectorTechnique,
    "memory": EpisodicMemoryTechnique,
    "multi_agent": MultiAgentTechnique,
}

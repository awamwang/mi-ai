"""多 Agent 注册表、口令路由与适配器。"""

from __future__ import annotations

from mi_ai.agents.config import AgentRegistry, load_agent_registry
from mi_ai.agents.routing_bot import RoutingBot

__all__ = [
    "AgentRegistry",
    "RoutingBot",
    "load_agent_registry",
]

"""适配器接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from mi_ai.agents.router import RouteDecision


class AgentAdapter(ABC):
    """将 RouteDecision 转为可播报文本。"""

    name: str

    @abstractmethod
    async def ask(self, decision: RouteDecision) -> str:
        pass

    async def ask_stream(self, decision: RouteDecision) -> AsyncIterator[str]:
        """默认整段返回；子类可覆盖为真流式。"""
        text = await self.ask(decision)
        if text:
            yield text

    def has_history(self) -> bool:
        return False

    def change_prompt(self, new_prompt: str) -> None:
        return None

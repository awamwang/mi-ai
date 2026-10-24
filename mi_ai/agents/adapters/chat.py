"""云端 OpenAI 兼容问答适配器（委托 xiaogpt ChatGPTBot）。"""

from __future__ import annotations

from typing import Any, AsyncIterator

from mi_ai.agents.adapters.base import AgentAdapter
from mi_ai.agents.router import RouteDecision


class ChatAdapter(AgentAdapter):
    def __init__(
        self,
        bot: Any,
        display_name: str = "大模型",
        *,
        prompt: str = "",
    ) -> None:
        self._bot = bot
        self.name = display_name
        self._prompt = (prompt or "").strip()

    def _with_prompt(self, query: str) -> str:
        if self._prompt and not self._bot.has_history():
            return f"{query},{self._prompt}"
        return query

    async def ask(self, decision: RouteDecision) -> str:
        answer = await self._bot.ask(self._with_prompt(decision.query))
        return answer or ""

    async def ask_stream(self, decision: RouteDecision) -> AsyncIterator[str]:
        async for chunk in self._bot.ask_stream(self._with_prompt(decision.query)):
            yield chunk

    def has_history(self) -> bool:
        return bool(self._bot.has_history())

    def change_prompt(self, new_prompt: str) -> None:
        self._bot.change_prompt(new_prompt)

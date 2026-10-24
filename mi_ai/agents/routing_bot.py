"""xiaogpt Bot 包装：按口令路由到注册表中的 Agent。"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, ClassVar

from xiaogpt.bot.base_bot import BaseBot

from mi_ai.agents.adapters.base import AgentAdapter
from mi_ai.agents.adapters.chat import ChatAdapter
from mi_ai.agents.adapters.cursor_adapter import CursorAdapter
from mi_ai.agents.config import AgentRegistry, load_agent_registry
from mi_ai.agents.router import RouteDecision, route_query

logger = logging.getLogger("mi_ai.agents")


class RoutingBot(BaseBot):
    """拦截 ask / ask_stream，先路由再调用对应适配器。"""

    name: ClassVar[str] = "智能助手"

    def __init__(
        self,
        chat_bot: BaseBot,
        registry: AgentRegistry | None = None,
        *,
        prompt: str = "",
    ) -> None:
        self._chat_bot = chat_bot
        self._registry = registry or load_agent_registry()
        self._prompt = prompt
        self._adapters = self._build_adapters()
        self._last_decision: RouteDecision | None = None
        # 实例级 name，供 TTS「正在问 xxx」使用
        self.name = "智能助手"

    @classmethod
    def from_config(cls, config: Any) -> RoutingBot:
        from xiaogpt.bot.chatgptapi_bot import ChatGPTBot

        prompt = getattr(config, "prompt", "") or ""
        return cls(ChatGPTBot.from_config(config), prompt=prompt)

    def _build_adapters(self) -> dict[str, AgentAdapter]:
        adapters: dict[str, AgentAdapter] = {}
        for agent in self._registry.agents.values():
            if not agent.enabled:
                continue
            kind = agent.type.lower()
            if kind in {"chat", "chatgpt", "openai"}:
                adapters[agent.id] = ChatAdapter(
                    self._chat_bot,
                    display_name="大模型",
                    prompt=self._prompt,
                )
            elif kind in {"cursor-local", "cursor", "cursor_local"}:
                adapters[agent.id] = CursorAdapter(
                    agent, self._registry, cloud=False
                )
            elif kind in {"cursor-cloud", "cursor_cloud", "cloud"}:
                adapters[agent.id] = CursorAdapter(
                    agent, self._registry, cloud=True
                )
            else:
                logger.warning("未知 Agent 类型 %s（%s），已跳过", agent.type, agent.id)
        if self._registry.default_id not in adapters:
            adapters[self._registry.default_id] = ChatAdapter(
                self._chat_bot,
                prompt=self._prompt,
            )
        return adapters

    def _decide(self, query: str) -> tuple[RouteDecision, AgentAdapter]:
        decision = route_query(query, self._registry)
        adapter = self._adapters.get(decision.agent.id)
        if adapter is None:
            disabled_id = decision.agent.id
            logger.warning("Agent「%s」未启用", disabled_id)
            message = (
                f"Agent「{disabled_id}」已在配置中关闭。"
                "若要用，请在 agents.yaml 里把 enabled 改为 true。"
            )

            class _DisabledAdapter(AgentAdapter):
                name = "智能助手"

                async def ask(self, _decision: RouteDecision) -> str:
                    return message

            adapter = _DisabledAdapter()
        self._last_decision = decision
        self.name = adapter.name
        logger.info(
            "路由 → %s%s | query=%s",
            decision.agent.id,
            f"/{decision.chat_name}" if decision.chat_name else "",
            decision.query[:80],
        )
        return decision, adapter

    async def ask(self, query: str, **options: Any) -> str:
        decision, adapter = self._decide(query)
        try:
            return await adapter.ask(decision)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent「%s」执行失败", decision.agent.id)
            return f"执行失败：{exc}"

    async def ask_stream(self, query: str, **options: Any) -> AsyncIterator[str]:
        decision, adapter = self._decide(query)
        try:
            async for chunk in adapter.ask_stream(decision):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent「%s」执行失败", decision.agent.id)
            yield f"执行失败：{exc}"

    def has_history(self) -> bool:
        # 恒为 True：阻止 xiaogpt 给所有问题追加 TTS 提示词；
        # chat 提示词改由 ChatAdapter 在首次提问时自行追加。
        return True

    def change_prompt(self, new_prompt: str) -> None:
        chat = self._adapters.get(self._registry.default_id)
        if chat is not None:
            chat.change_prompt(new_prompt)

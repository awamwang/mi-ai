"""Cursor Local / Cloud 适配器（cursor-sdk）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mi_ai.agents.adapters.base import AgentAdapter
from mi_ai.agents.bindings import get_last_agent_id, set_chat_id, set_last_agent_id
from mi_ai.agents.config import AgentDef, AgentRegistry
from mi_ai.agents.router import RouteDecision
from mi_ai.settings import ROOT_DIR

logger = logging.getLogger("mi_ai.agents.cursor")

# 音箱播报不宜过长
_MAX_TTS_CHARS = 280


def _voice_summary(text: str) -> str:
    text = (text or "").strip().replace("\n", "，")
    if not text:
        return "Cursor 没有返回内容。"
    if len(text) <= _MAX_TTS_CHARS:
        return text
    return text[:_MAX_TTS_CHARS].rstrip("，,。. ") + "。后面还有，请在电脑上查看完整结果。"


class CursorAdapter(AgentAdapter):
    def __init__(
        self,
        agent_def: AgentDef,
        registry: AgentRegistry,
        *,
        cloud: bool,
    ) -> None:
        self._def = agent_def
        self._registry = registry
        self._cloud = cloud
        self.name = "Cursor云端" if cloud else "Cursor"

    def _cwd(self) -> str:
        raw = self._def.cwd.strip()
        if raw:
            return str(Path(raw).expanduser().resolve())
        return str(ROOT_DIR)

    def _api_key(self) -> str:
        key = self._registry.cursor_api_key
        if not key:
            raise RuntimeError(
                "未配置 CURSOR_API_KEY。请在 .env 或 agents.yaml 中填写。"
            )
        return key

    def _model_selection(self) -> Any:
        """构建 SDK model：auto-smart 走 Cursor Router。"""
        from cursor_sdk import ModelParameterValue, ModelSelection  # type: ignore[import-untyped]

        model_id = self._def.model
        if model_id == "auto-smart":
            mode = (self._def.optimize_for or "balanced").strip().lower()
            return ModelSelection(
                id="auto-smart",
                params=[ModelParameterValue(id="optimize_for", value=mode)],
            )
        if self._def.optimize_for:
            return ModelSelection(
                id=model_id,
                params=[
                    ModelParameterValue(
                        id="optimize_for",
                        value=self._def.optimize_for,
                    )
                ],
            )
        return model_id

    def _pick_resume_id(self, decision: RouteDecision) -> str | None:
        if decision.resume_agent_id:
            return decision.resume_agent_id
        if self._def.resume_policy == "last":
            return get_last_agent_id(self._def.id)
        return None

    def _build_prompt(self, decision: RouteDecision) -> str:
        prompt = decision.query.strip()
        if not prompt:
            return ""
        return (
            f"{prompt}\n\n"
            "（来自小爱音箱语音指令。请用中文简洁回复最终结论，"
            "适合口语播报，控制在 200 字内；细节可写在代码/文件中。）"
        )

    async def ask(self, decision: RouteDecision) -> str:
        try:
            from cursor_sdk import (  # type: ignore[import-untyped]
                AsyncClient,
                CloudAgentOptions,
                CloudRepository,
                LocalAgentOptions,
            )
        except ImportError as exc:
            raise RuntimeError(
                "未安装 cursor-sdk，请执行：pip install cursor-sdk"
            ) from exc

        if decision.session_switch_only:
            name = decision.chat_name or "该"
            # 特征词单独出现：只切会话，不向 Cursor 提问
            if decision.resume_agent_id:
                return f"好，已切换到「{name}」。"
            return f"好，已准备「{name}」会话，下次直接说任务即可。"

        api_key = self._api_key()
        model = self._model_selection()
        resume_id = self._pick_resume_id(decision)
        prompt = self._build_prompt(decision)
        if not prompt:
            return "请说明要让 Cursor 做什么。"

        if self._cloud:
            result_text, agent_id_used = await self._run_cloud(
                AsyncClient,
                CloudAgentOptions,
                CloudRepository,
                api_key=api_key,
                model=model,
                resume_id=resume_id,
                prompt=prompt,
            )
        else:
            result_text, agent_id_used = await self._run_local(
                AsyncClient,
                LocalAgentOptions,
                api_key=api_key,
                model=model,
                cwd=self._cwd(),
                resume_id=resume_id,
                prompt=prompt,
            )

        if agent_id_used:
            set_last_agent_id(self._def.id, agent_id_used)
            if decision.chat_name:
                set_chat_id(self._def.id, decision.chat_name, agent_id_used)
                logger.info(
                    "已绑定聊天「%s」→ %s",
                    decision.chat_name,
                    agent_id_used,
                )

        prefix = ""
        if decision.chat_name and agent_id_used:
            prefix = f"已在「{decision.chat_name}」会话处理。"
        elif agent_id_used:
            prefix = f"会话 {agent_id_used[:16]}。"

        body = _voice_summary(result_text)
        return f"{prefix}{body}" if prefix else body

    async def _run_local(
        self,
        AsyncClient: Any,
        LocalAgentOptions: Any,
        *,
        api_key: str,
        model: str,
        cwd: str,
        resume_id: str | None,
        prompt: str,
    ) -> tuple[str, str | None]:
        async with await AsyncClient.launch_bridge(workspace=cwd) as client:
            if resume_id:
                agent = await client.resume_agent(
                    resume_id,
                    {
                        "model": model,
                        "api_key": api_key,
                        "local": LocalAgentOptions(cwd=cwd),
                    },
                )
            else:
                agent = await client.create_agent(
                    model=model,
                    api_key=api_key,
                    local=LocalAgentOptions(cwd=cwd),
                )
            async with agent:
                run = await agent.send(prompt)
                text = await run.text()
                agent_id = getattr(agent, "agent_id", None)
                return (text or ""), agent_id

    async def _run_cloud(
        self,
        AsyncClient: Any,
        CloudAgentOptions: Any,
        CloudRepository: Any,
        *,
        api_key: str,
        model: str,
        resume_id: str | None,
        prompt: str,
    ) -> tuple[str, str | None]:
        repos = [
            CloudRepository(url=r.url, starting_ref=r.starting_ref)
            for r in self._def.repos
        ]
        cloud_opts = CloudAgentOptions(
            repos=repos,
            auto_create_pr=self._def.auto_create_pr,
        )

        # Cloud 不依赖本机 bridge；用默认同步 Agent API 包一层异步
        import asyncio

        from cursor_sdk import Agent  # type: ignore[import-untyped]

        def _sync_run() -> tuple[str, str | None]:
            if resume_id:
                agent = Agent.resume(
                    resume_id,
                    {
                        "model": model,
                        "api_key": api_key,
                        "cloud": cloud_opts,
                    },
                )
            else:
                agent = Agent.create(
                    model=model,
                    api_key=api_key,
                    cloud=cloud_opts,
                )
            with agent:
                run = agent.send(prompt)
                text = run.text()
                return (text or ""), getattr(agent, "agent_id", None)

        return await asyncio.to_thread(_sync_run)

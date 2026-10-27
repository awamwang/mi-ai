"""Cursor Local / Cloud 适配器（cursor-sdk）。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from mi_ai.agents.adapters.base import AgentAdapter
from mi_ai.agents.bindings import get_last_agent_id, set_chat_id, set_last_agent_id
from mi_ai.agents.config import AgentDef, AgentRegistry
from mi_ai.agents.router import RouteDecision
from mi_ai.settings import ROOT_DIR

logger = logging.getLogger("mi_ai.agents.cursor")

# 音箱播报不宜过长
_MAX_TTS_CHARS = 280
# 流式心跳间隔：空串不进 TTS，但让 xiaogpt 有机会发现新语音并打断
_HEARTBEAT_SEC = 1.0
# 取消同会话旧 run 后最多等待收尾
_CANCEL_WAIT_SEC = 20.0


def _voice_summary(text: str) -> str:
    text = (text or "").strip().replace("\n", "，")
    if not text:
        return "Cursor 没有返回内容。"
    if len(text) <= _MAX_TTS_CHARS:
        return text
    return text[:_MAX_TTS_CHARS].rstrip("，,。. ") + "。后面还有，请在电脑上查看完整结果。"


@dataclass
class _ActiveHandle:
    """同一会话上正在执行的 Cursor run。"""

    task: asyncio.Task[str] | None = None
    run: Any | None = None
    run_id: str | None = None
    agent_id: str | None = None
    cancelled: bool = False

    def attach_run(self, run: Any, agent_id: str | None = None) -> None:
        self.run = run
        self.run_id = getattr(run, "run_id", None) or getattr(run, "id", None)
        if agent_id is not None:
            self.agent_id = agent_id
        elif getattr(run, "agent_id", None):
            self.agent_id = run.agent_id


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
        # 会话键 → 进行中的 run；仅同键新指令会取消旧 run
        self._active: dict[str, _ActiveHandle] = {}
        self._active_guard = asyncio.Lock()

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

    def _session_key(self, decision: RouteDecision) -> str:
        """同一 Cursor 会话的稳定键：优先聊天名，否则 resume id。"""
        if decision.chat_name:
            return f"chat:{decision.chat_name}"
        resume_id = self._pick_resume_id(decision)
        if resume_id:
            return f"id:{resume_id}"
        return "anon:default"

    def _build_prompt(self, decision: RouteDecision) -> str:
        prompt = decision.query.strip()
        if not prompt:
            return ""
        return (
            f"{prompt}\n\n"
            "（来自小爱音箱语音指令。请用中文简洁回复最终结论，"
            "适合口语播报，控制在 200 字内；细节可写在代码/文件中。）"
        )

    def _switch_only_reply(self, decision: RouteDecision) -> str:
        name = decision.chat_name or "该"
        # 特征词单独出现：只切会话，不向 Cursor 提问，也不取消进行中的 run
        if decision.resume_agent_id:
            return f"好，已切换到「{name}」。"
        return f"好，已准备「{name}」会话，下次直接说任务即可。"

    def _format_reply(
        self,
        decision: RouteDecision,
        result_text: str,
        agent_id_used: str | None,
    ) -> str:
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

    async def _cancel_handle(self, key: str, handle: _ActiveHandle) -> None:
        """取消并等待指定会话上的旧 run 收尾。"""
        handle.cancelled = True
        run = handle.run
        try:
            if run is not None and hasattr(run, "supports") and run.supports("cancel"):
                cancel = run.cancel
                if asyncio.iscoroutinefunction(cancel):
                    await cancel()
                else:
                    await asyncio.to_thread(cancel)
                logger.info("已取消会话 %s 上未完成的 Cursor run", key)
            elif handle.run_id:
                from cursor_sdk import Agent  # type: ignore[import-untyped]

                await asyncio.to_thread(
                    Agent.cancel_run,
                    handle.run_id,
                    agent_id=handle.agent_id,
                )
                logger.info("已取消会话 %s 上未完成的 Cursor run（按 run_id）", key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("取消会话 %s 的 Cursor run 失败：%s", key, exc)

        task = handle.task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=_CANCEL_WAIT_SEC,
                )
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _cancel_session(self, key: str) -> None:
        """若该会话仍有未完成 run，则取消。"""
        async with self._active_guard:
            handle = self._active.pop(key, None)
        if handle is None:
            return
        await self._cancel_handle(key, handle)

    def _forget_handle(self, key: str, handle: _ActiveHandle) -> None:
        current = self._active.get(key)
        if current is handle:
            self._active.pop(key, None)

    def _ensure_sdk(self) -> tuple[Any, Any, Any, Any]:
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
        return AsyncClient, CloudAgentOptions, CloudRepository, LocalAgentOptions

    async def _spawn(
        self,
        decision: RouteDecision,
        prompt: str,
    ) -> tuple[str, _ActiveHandle, asyncio.Task[str]]:
        """取消同会话旧任务后启动新 run，返回 (session_key, handle, task)。"""
        AsyncClient, CloudAgentOptions, CloudRepository, LocalAgentOptions = (
            self._ensure_sdk()
        )
        key = self._session_key(decision)
        await self._cancel_session(key)

        api_key = self._api_key()
        model = self._model_selection()
        resume_id = self._pick_resume_id(decision)
        handle = _ActiveHandle()

        async def _job() -> str:
            try:
                if self._cloud:
                    result_text, agent_id_used = await self._run_cloud(
                        CloudAgentOptions,
                        CloudRepository,
                        api_key=api_key,
                        model=model,
                        resume_id=resume_id,
                        prompt=prompt,
                        handle=handle,
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
                        handle=handle,
                    )
            except Exception:
                if handle.cancelled:
                    return "好的，已停下上一轮。"
                raise

            if handle.cancelled:
                return "好的，已停下上一轮。"
            return self._format_reply(decision, result_text, agent_id_used)

        task = asyncio.create_task(_job())
        handle.task = task
        async with self._active_guard:
            self._active[key] = handle
        return key, handle, task

    async def ask(self, decision: RouteDecision) -> str:
        if decision.session_switch_only:
            return self._switch_only_reply(decision)

        prompt = self._build_prompt(decision)
        if not prompt:
            return "请说明要让 Cursor 做什么。"

        key, handle, task = await self._spawn(decision, prompt)
        try:
            return await task
        except asyncio.CancelledError:
            # 被其它话题打断时：保留同会话后台 run，供下次同会话指令取消
            raise
        finally:
            if task.done() and not task.cancelled():
                self._forget_handle(key, handle)

    async def ask_stream(self, decision: RouteDecision) -> AsyncIterator[str]:
        """流式出口：心跳空串 + 完成后的摘要；同会话新指令会先取消旧 run。"""
        if decision.session_switch_only:
            text = self._switch_only_reply(decision)
            if text:
                yield text
            return

        prompt = self._build_prompt(decision)
        if not prompt:
            yield "请说明要让 Cursor 做什么。"
            return

        key, handle, task = await self._spawn(decision, prompt)
        try:
            while not task.done():
                # 空串：xiaogpt 不播报，但能轮询到新语音并打断当前流
                yield ""
                await asyncio.wait({task}, timeout=_HEARTBEAT_SEC)
            yield task.result()
        except asyncio.CancelledError:
            # 其它话题插入：不取消本会话 Cursor，留给下次同会话指令处理
            raise
        else:
            self._forget_handle(key, handle)

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
        handle: _ActiveHandle | None = None,
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
                agent_id = getattr(agent, "agent_id", None)
                if handle is not None:
                    handle.attach_run(run, agent_id)
                text = await run.text()
                return (text or ""), agent_id

    async def _run_cloud(
        self,
        CloudAgentOptions: Any,
        CloudRepository: Any,
        *,
        api_key: str,
        model: str,
        resume_id: str | None,
        prompt: str,
        handle: _ActiveHandle | None = None,
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
                agent_id = getattr(agent, "agent_id", None)
                if handle is not None:
                    handle.attach_run(run, agent_id)
                text = run.text()
                return (text or ""), agent_id

        return await asyncio.to_thread(_sync_run)

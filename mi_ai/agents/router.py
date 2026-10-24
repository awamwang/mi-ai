"""从用户口令中解析目标 Agent 与命名聊天。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mi_ai.agents.bindings import get_chat_id, list_chats
from mi_ai.agents.config import AgentDef, AgentRegistry


@dataclass(frozen=True)
class RouteDecision:
    """一次路由结果。"""

    agent: AgentDef
    chat_name: str | None
    resume_agent_id: str | None
    query: str
    matched_alias: str | None
    explicit: bool


_PREFIX_RE = re.compile(
    r"^(?:请|帮我|麻烦|我想|我要)?(?:用|让|叫|交给|通过)?",
    re.IGNORECASE,
)
_CHAT_MARKERS = ("聊天", "对话", "会话", "窗口")
_EXEC_MARKERS = ("执行", "运行", "去做", "去做一下", "帮我", "请")


def _strip_noise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _known_chat_names(agent: AgentDef) -> list[str]:
    names = set(agent.chats.keys())
    names.update(list_chats(agent.id).keys())
    # 长名优先，避免短名误伤
    return sorted(names, key=len, reverse=True)


def _find_alias(text: str, agent: AgentDef) -> tuple[str | None, int, int]:
    """返回 (alias, start, end)；未找到则 alias=None。"""
    best: tuple[str, int, int] | None = None
    lowered = text.lower()
    for alias in sorted(agent.aliases, key=len, reverse=True):
        if not alias:
            continue
        pos = lowered.find(alias.lower())
        if pos < 0:
            pos = text.find(alias)
        if pos < 0:
            continue
        end = pos + len(alias)
        if best is None or len(alias) > len(best[0]) or (
            len(alias) == len(best[0]) and pos < best[1]
        ):
            best = (alias, pos, end)
    if best is None:
        return None, -1, -1
    return best


def _extract_chat_after_alias(
    text: str,
    alias_end: int,
    chat_names: list[str],
) -> tuple[str | None, int]:
    """解析「在{chat}里」「继续{chat}」；返回 (chat_name, rest_start)。"""
    rest = text[alias_end:]
    rest_lstrip = rest.lstrip(" ，,：:")
    consumed = len(rest) - len(rest_lstrip)
    base = alias_end + consumed
    chunk = text[base:]

    # 在{chat}(聊天|...)?里/中  —— 「里/中」必填，避免「在登」误切
    m = re.match(
        r"^(?:在|到)(?P<name>.+?)(?:聊天|对话|会话|窗口)?(?:里|中|内)(?:执行|运行|去)?",
        chunk,
    )
    if m:
        name = m.group("name").strip(" 的")
        for known in chat_names:
            if name == known or name.startswith(known) or known in name:
                return known, base + m.end()
        # 未知名也允许：稍后新建并绑定
        if name and len(name) <= 20:
            return name, base + m.end()

    # 继续{chat}
    m2 = re.match(r"^继续(?P<name>\S{1,20})", chunk)
    if m2:
        name = m2.group("name").strip()
        for marker in _CHAT_MARKERS + _EXEC_MARKERS:
            if name.endswith(marker):
                name = name[: -len(marker)]
        for known in chat_names:
            if name == known or name.startswith(known):
                return known, base + m2.end()
        if name:
            return name, base + m2.end()

    # 直接跟已知聊天名
    for known in chat_names:
        if chunk.startswith(known):
            return known, base + len(known)

    return None, base


def _strip_exec_prefix(text: str) -> str:
    t = text.lstrip(" ，,：:")
    for marker in _EXEC_MARKERS:
        if t.startswith(marker):
            t = t[len(marker) :].lstrip(" ，,：:")
            break
    for marker in _CHAT_MARKERS:
        if t.startswith(marker):
            t = t[len(marker) :].lstrip("里中内 ，,：:")
    return t.strip(" ？?。.!！")


def _resolve_resume_id(agent: AgentDef, chat_name: str | None) -> str | None:
    if not chat_name:
        return None
    if chat_name in agent.chats:
        return agent.chats[chat_name]
    return get_chat_id(agent.id, chat_name)


def route_query(query: str, registry: AgentRegistry) -> RouteDecision:
    """根据口令选择 Agent；未点名则走 default。"""
    text = _strip_noise(query)
    if not text:
        agent = registry.agents[registry.default_id]
        return RouteDecision(
            agent=agent,
            chat_name=None,
            resume_agent_id=None,
            query="",
            matched_alias=None,
            explicit=False,
        )

    # 先尝试每个启用 Agent 的别名（最长优先由 resolve_alias 完成）
    matched_agent = registry.resolve_alias(text)
    if matched_agent is None:
        agent = registry.agents[registry.default_id]
        return RouteDecision(
            agent=agent,
            chat_name=None,
            resume_agent_id=None,
            query=text,
            matched_alias=None,
            explicit=False,
        )

    alias, start, end = _find_alias(text, matched_agent)
    # 若别名不在句首附近，仍视为显式路由，但尽量剥掉别名段
    chat_names = _known_chat_names(matched_agent)
    chat_name, rest_start = _extract_chat_after_alias(text, end, chat_names)
    rest = _strip_exec_prefix(text[rest_start:])

    # 去掉别名前缀废话：「帮我用」
    prefix = text[:start]
    if prefix and not rest:
        # 例如整句只有「用 cursor」
        rest = ""
    elif not rest and start > 0:
        # 别名在中间：取别名后内容；若空则取别名前内容
        rest = _strip_exec_prefix(text[end:]) or _strip_noise(
            _PREFIX_RE.sub("", text[:start])
        )

    # 清理 rest 里残留的别名
    if alias and rest.lower().startswith(alias.lower()):
        rest = rest[len(alias) :].lstrip()
    rest = _strip_exec_prefix(rest)

    resume_id = _resolve_resume_id(matched_agent, chat_name)
    return RouteDecision(
        agent=matched_agent,
        chat_name=chat_name,
        resume_agent_id=resume_id,
        query=rest or text,
        matched_alias=alias,
        explicit=True,
    )

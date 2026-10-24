"""加载 agents.yaml 注册表。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mi_ai.settings import ROOT_DIR

AGENTS_CONFIG_PATH = ROOT_DIR / "agents.yaml"
AGENTS_EXAMPLE_PATH = ROOT_DIR / "agents.example.yaml"


@dataclass(frozen=True)
class CloudRepoConfig:
    url: str
    starting_ref: str = "main"


@dataclass(frozen=True)
class AgentDef:
    """单个可路由后端定义。"""

    id: str
    type: str
    enabled: bool
    aliases: tuple[str, ...]
    cwd: str = ""
    model: str = "default"
    # Cursor Router（auto-smart）模式：cost / balanced / intelligence；非 Router 可留空
    optimize_for: str | None = None
    resume_policy: str = "last"  # new | last
    chats: dict[str, str] = field(default_factory=dict)
    # 特征入口词 → 聊天名；词本身不送进模型，只负责切到该会话
    entry_phrases: dict[str, str] = field(default_factory=dict)
    repos: tuple[CloudRepoConfig, ...] = ()
    auto_create_pr: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class AgentRegistry:
    """已启用的 Agent 集合 + 默认项。"""

    default_id: str
    agents: dict[str, AgentDef]
    cursor_api_key: str
    source_path: Path

    def get(self, agent_id: str) -> AgentDef | None:
        return self.agents.get(agent_id)

    def enabled_agents(self) -> list[AgentDef]:
        return [a for a in self.agents.values() if a.enabled]

    def resolve_alias(
        self, text: str, *, include_disabled: bool = True
    ) -> AgentDef | None:
        """在文本中找最长匹配别名。

        默认也扫描已禁用 Agent，避免「云端cursor」被短别名「cursor」误匹配。
        """
        lowered = text.lower()
        best: AgentDef | None = None
        best_len = -1
        best_pos = 10**9
        agents = self.agents.values() if include_disabled else self.enabled_agents()
        for agent in agents:
            for alias in agent.aliases:
                if not alias:
                    continue
                pos = lowered.find(alias.lower())
                if pos < 0:
                    pos = text.find(alias)
                if pos < 0:
                    continue
                if len(alias) > best_len or (len(alias) == best_len and pos < best_pos):
                    best = agent
                    best_len = len(alias)
                    best_pos = pos
        return best


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_agent(agent_id: str, raw: dict[str, Any]) -> AgentDef:
    aliases_raw = raw.get("aliases") or []
    if isinstance(aliases_raw, str):
        aliases = tuple(a.strip() for a in aliases_raw.split(",") if a.strip())
    else:
        aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip())
    if agent_id not in aliases:
        aliases = (agent_id, *aliases)

    chats_raw = raw.get("chats") or {}
    chats: dict[str, str] = {}
    if isinstance(chats_raw, dict):
        for name, aid in chats_raw.items():
            key = str(name).strip()
            if not key:
                continue
            if aid is None or str(aid).strip() in {"", "null", "None"}:
                continue
            chats[key] = str(aid).strip()

    entry_phrases = _parse_entry_phrases(raw.get("entry_phrases"))
    # 特征词自动并入 aliases，便于口令匹配
    extra_aliases = tuple(
        p for p in entry_phrases if p and p not in aliases
    )
    if extra_aliases:
        aliases = (*aliases, *extra_aliases)

    repos: list[CloudRepoConfig] = []
    for item in raw.get("repos") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        repos.append(
            CloudRepoConfig(
                url=url,
                starting_ref=str(item.get("starting_ref") or "main").strip() or "main",
            )
        )

    model_id, optimize_for = _parse_model(raw)

    return AgentDef(
        id=agent_id,
        type=str(raw.get("type") or agent_id).strip(),
        enabled=_as_bool(raw.get("enabled"), True),
        aliases=aliases,
        cwd=str(raw.get("cwd") or "").strip(),
        model=model_id,
        optimize_for=optimize_for,
        resume_policy=str(raw.get("resume_policy") or "last").strip().lower() or "last",
        chats=chats,
        entry_phrases=entry_phrases,
        repos=tuple(repos),
        auto_create_pr=_as_bool(raw.get("auto_create_pr"), False),
        raw=dict(raw),
    )


def _parse_entry_phrases(raw: Any) -> dict[str, str]:
    """解析特征入口词。

    支持：
    - 列表：``[小爱编程]`` → 聊天名同名
    - 映射：``{小爱编程: 绘画}`` 或 ``{小爱编程: agent-xxx}``
      若值以 agent-/bc- 开头，聊天名仍用特征词，agent_id 应写在 chats 里更清晰；
      这里值一律当作聊天名。
    """
    result: dict[str, str] = {}
    if raw is None:
        return result
    if isinstance(raw, str):
        for part in raw.split(","):
            phrase = part.strip()
            if phrase:
                result[phrase] = phrase
        return result
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                phrase = item.strip()
                result[phrase] = phrase
            elif isinstance(item, dict):
                for k, v in item.items():
                    phrase = str(k).strip()
                    if not phrase:
                        continue
                    chat = str(v).strip() if v is not None else phrase
                    result[phrase] = chat or phrase
        return result
    if isinstance(raw, dict):
        for k, v in raw.items():
            phrase = str(k).strip()
            if not phrase:
                continue
            if v is None or str(v).strip() in {"", "null", "None"}:
                result[phrase] = phrase
            else:
                result[phrase] = str(v).strip()
    return result


def _parse_model(raw: dict[str, Any]) -> tuple[str, str | None]:
    """解析 model / optimize_for。

    默认 ``default``（服务端 Auto）。Teams Router 可用 ``auto-smart`` + optimize_for。
    """
    model_raw = raw.get("model", "default")
    optimize_raw = raw.get("optimize_for")

    if isinstance(model_raw, dict):
        model_id = str(model_raw.get("id") or "default").strip() or "default"
        if optimize_raw is None:
            optimize_raw = model_raw.get("optimize_for")
    else:
        model_id = str(model_raw or "default").strip() or "default"

    # 常见别名：个人账号 Auto 多用 default；Teams Router 用 auto-smart
    aliases = {
        "auto": "default",
        "router": "auto-smart",
        "cursor-auto": "default",
        "自动": "default",
    }
    model_id = aliases.get(model_id.lower(), model_id)

    optimize_for: str | None
    if optimize_raw is None or str(optimize_raw).strip() == "":
        optimize_for = "balanced" if model_id == "auto-smart" else None
    else:
        optimize_for = str(optimize_raw).strip().lower()
        optimize_map = {
            "balance": "balanced",
            "均衡": "balanced",
            "成本": "cost",
            "智能": "intelligence",
            "质量": "intelligence",
        }
        optimize_for = optimize_map.get(optimize_for, optimize_for)

    if model_id != "auto-smart" and (
        optimize_raw is None or str(optimize_raw).strip() == ""
    ):
        optimize_for = None

    return model_id, optimize_for


def resolve_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    env = os.getenv("MI_AI_AGENTS_CONFIG", "").strip()
    if env:
        return Path(env).expanduser()
    if AGENTS_CONFIG_PATH.is_file():
        return AGENTS_CONFIG_PATH
    return AGENTS_EXAMPLE_PATH


def load_agent_registry(path: Path | None = None) -> AgentRegistry:
    """加载注册表；无文件时回退到仅 chat 默认。"""
    # 确保 CURSOR_API_KEY 等可从 .env 读到（CLI / 适配器共用）
    try:
        from dotenv import load_dotenv

        env_file = ROOT_DIR / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)
    except Exception:
        pass

    cfg_path = resolve_config_path(path)
    if not cfg_path.is_file():
        chat = AgentDef(
            id="chat",
            type="chat",
            enabled=True,
            aliases=("chat", "问答", "聊天", "大模型"),
        )
        return AgentRegistry(
            default_id="chat",
            agents={"chat": chat},
            cursor_api_key=os.getenv("CURSOR_API_KEY", "").strip(),
            source_path=cfg_path,
        )

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"agents 配置格式错误：{cfg_path}")

    agents_raw = data.get("agents") or {}
    if not isinstance(agents_raw, dict) or not agents_raw:
        raise SystemExit(f"agents 配置缺少 agents 段：{cfg_path}")

    agents: dict[str, AgentDef] = {}
    for agent_id, raw in agents_raw.items():
        if not isinstance(raw, dict):
            raise SystemExit(f"Agent「{agent_id}」配置必须是对象：{cfg_path}")
        agents[str(agent_id)] = _parse_agent(str(agent_id), raw)

    default_id = str(data.get("default") or "chat").strip()
    if default_id not in agents:
        raise SystemExit(f"default「{default_id}」不在 agents 中：{cfg_path}")
    if not agents[default_id].enabled:
        raise SystemExit(f"default「{default_id}」已禁用，请换一个启用中的 Agent")

    api_key = str(data.get("cursor_api_key") or "").strip()
    if not api_key:
        api_key = os.getenv("CURSOR_API_KEY", "").strip()

    return AgentRegistry(
        default_id=default_id,
        agents=agents,
        cursor_api_key=api_key,
        source_path=cfg_path,
    )

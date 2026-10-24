"""命名聊天 ↔ Cursor agent_id 绑定（持久化到 data/）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mi_ai.paths import DATA_DIR, ensure_data_dir

BINDINGS_PATH = DATA_DIR / "agent_chat_bindings.json"


def _empty() -> dict[str, Any]:
    return {"agents": {}}


def load_bindings(path: Path | None = None) -> dict[str, Any]:
    file = path or BINDINGS_PATH
    if not file.is_file():
        return _empty()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    agents = data.get("agents")
    if not isinstance(agents, dict):
        data["agents"] = {}
    return data


def save_bindings(data: dict[str, Any], path: Path | None = None) -> Path:
    ensure_data_dir()
    file = path or BINDINGS_PATH
    file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return file


def get_chat_id(agent_key: str, chat_name: str, path: Path | None = None) -> str | None:
    data = load_bindings(path)
    agent = data.get("agents", {}).get(agent_key) or {}
    chats = agent.get("chats") or {}
    value = chats.get(chat_name)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def set_chat_id(
    agent_key: str,
    chat_name: str,
    agent_id: str,
    path: Path | None = None,
) -> Path:
    data = load_bindings(path)
    agents = data.setdefault("agents", {})
    agent = agents.setdefault(agent_key, {})
    chats = agent.setdefault("chats", {})
    chats[chat_name] = agent_id
    return save_bindings(data, path)


def get_last_agent_id(agent_key: str, path: Path | None = None) -> str | None:
    data = load_bindings(path)
    agent = data.get("agents", {}).get(agent_key) or {}
    value = agent.get("last_agent_id")
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def set_last_agent_id(
    agent_key: str,
    agent_id: str,
    path: Path | None = None,
) -> Path:
    data = load_bindings(path)
    agents = data.setdefault("agents", {})
    agent = agents.setdefault(agent_key, {})
    agent["last_agent_id"] = agent_id
    return save_bindings(data, path)


def list_chats(agent_key: str, path: Path | None = None) -> dict[str, str]:
    data = load_bindings(path)
    agent = data.get("agents", {}).get(agent_key) or {}
    chats = agent.get("chats") or {}
    return {str(k): str(v) for k, v in chats.items() if v}

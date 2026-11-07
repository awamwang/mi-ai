"""读写 .env：按键更新并尽量保留原注释与顺序。"""

from __future__ import annotations

import re
from pathlib import Path

from mi_ai.settings import ENV_PATH

# 控制台允许写入的配置键
WRITABLE_KEYS: frozenset[str] = frozenset(
    {
        "MI_USER",
        "MI_PASS",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_MODEL",
        "KEYWORDS",
        "PROMPT",
        "START_CONVERSATION",
        "END_CONVERSATION",
        "HTTP_PROXY",
        "VERBOSE",
        "LX06_DID",
        "LX06_HARDWARE",
        "LX06_MUTE_XIAOAI",
        "LX06_STREAM",
        "LX06_USE_COMMAND",
        "L05C_DID",
        "L05C_HARDWARE",
        "L05C_MUTE_XIAOAI",
        "L05C_STREAM",
        "L05C_USE_COMMAND",
        "MI_AI_DEVICES",
        "MI_AI_RESTART_BASE_SEC",
        "MI_AI_RESTART_MAX_SEC",
        "MI_AI_LOG_DIR",
        "MI_AI_LOG_KEEP_DAYS",
        "MI_AI_AUTH_CHECK_MINUTES",
        "MI_AI_CONSOLE",
        "MI_AI_CONSOLE_HOST",
        "MI_AI_CONSOLE_PORT",
        "CURSOR_API_KEY",
    }
)

_SECRET_KEYS = frozenset({"MI_PASS", "OPENAI_API_KEY", "CURSOR_API_KEY", "MI_COOKIE"})
_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def mask_secret(value: str, keep: int = 4) -> str:
    """脱敏展示。"""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * max(4, len(value) - keep) + value[-keep:]


def parse_env_map(path: Path | None = None) -> dict[str, str]:
    """解析 .env 为键值（后出现的同名键覆盖前者）。"""
    target = path or ENV_PATH
    result: dict[str, str] = {}
    if not target.is_file():
        return result
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def _format_value(value: str) -> str:
    if value == "":
        return ""
    if any(ch in value for ch in ' \t#"\'\\'):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def update_env_keys(updates: dict[str, str], path: Path | None = None) -> list[str]:
    """按白名单更新 .env；返回实际写入的键名列表。"""
    target = path or ENV_PATH
    filtered = {
        k: "" if v is None else str(v)
        for k, v in updates.items()
        if k in WRITABLE_KEYS
    }
    if not filtered:
        return []

    lines: list[str] = []
    if target.is_file():
        lines = target.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    new_lines: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            m = _LINE_RE.match(stripped)
            if m and m.group(1) in filtered:
                key = m.group(1)
                new_lines.append(f"{key}={_format_value(filtered[key])}")
                seen.add(key)
                continue
        new_lines.append(raw)

    missing = [k for k in filtered if k not in seen]
    if missing:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append("# ========== 控制台写入 ==========")
        for key in missing:
            new_lines.append(f"{key}={_format_value(filtered[key])}")

    text = "\n".join(new_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return sorted(filtered.keys())


def public_config_view(env_map: dict[str, str] | None = None) -> dict[str, str]:
    """返回可展示的配置（密钥脱敏）。"""
    data = dict(env_map or parse_env_map())
    out: dict[str, str] = {}
    for key in sorted(set(data) | WRITABLE_KEYS):
        if key not in data and key not in WRITABLE_KEYS:
            continue
        value = data.get(key, "")
        if key in _SECRET_KEYS:
            out[key] = mask_secret(value)
        else:
            out[key] = value
    return out

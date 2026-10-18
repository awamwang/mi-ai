"""从 ENV / .env 加载项目配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

# 音箱配置前缀：环境变量形如 LX06_DID、L05C_STREAM
SPEAKER_PROFILES = ("LX06", "L05C")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_keywords(raw: str) -> tuple[str, ...]:
    parts = [p.strip() for p in raw.split(",")]
    return tuple(p for p in parts if p)


@dataclass(frozen=True)
class SpeakerConfig:
    """单台音箱的运行参数。"""

    name: str
    did: str
    hardware: str
    mute_xiaoai: bool
    stream: bool
    use_command: bool


@dataclass(frozen=True)
class AppSettings:
    """全局配置。"""

    mi_user: str
    mi_pass: str
    mi_cookie: str
    openai_api_key: str
    openai_api_base: str
    openai_model: str
    keywords: tuple[str, ...]
    prompt: str
    start_conversation: str
    end_conversation: str
    http_proxy: str
    verbose: int
    speakers: dict[str, SpeakerConfig]


def load_settings(env_file: Path | None = None) -> AppSettings:
    """加载 .env 并构建配置；不存在的键使用合理默认值。"""
    path = env_file or ENV_PATH
    if path.is_file():
        load_dotenv(path, override=True)
    else:
        load_dotenv(override=False)

    speakers: dict[str, SpeakerConfig] = {}
    for name in SPEAKER_PROFILES:
        prefix = name
        default_stream = name == "LX06"
        default_use_command = name == "L05C"
        speakers[name] = SpeakerConfig(
            name=name,
            did=os.getenv(f"{prefix}_DID", "").strip(),
            hardware=os.getenv(f"{prefix}_HARDWARE", name).strip() or name,
            mute_xiaoai=_as_bool(os.getenv(f"{prefix}_MUTE_XIAOAI"), True),
            stream=_as_bool(os.getenv(f"{prefix}_STREAM"), default_stream),
            use_command=_as_bool(os.getenv(f"{prefix}_USE_COMMAND"), default_use_command),
        )

    return AppSettings(
        mi_user=os.getenv("MI_USER", "").strip(),
        mi_pass=os.getenv("MI_PASS", "").strip(),
        mi_cookie=os.getenv("MI_COOKIE", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_api_base=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        keywords=_split_keywords(os.getenv("KEYWORDS", "帮我,请")),
        prompt=os.getenv(
            "PROMPT",
            "以下请用 300 字以内回答，请只回答文字不要带链接",
        ).strip(),
        start_conversation=os.getenv("START_CONVERSATION", "开始持续对话").strip(),
        end_conversation=os.getenv("END_CONVERSATION", "结束持续对话").strip(),
        http_proxy=os.getenv("HTTP_PROXY", "").strip(),
        verbose=int(os.getenv("VERBOSE", "1") or "1"),
        speakers=speakers,
    )


def require_cloud_llm(settings: AppSettings) -> None:
    """校验云端大模型必填项。"""
    missing: list[str] = []
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.openai_api_base:
        missing.append("OPENAI_API_BASE")
    if missing:
        raise SystemExit(
            "缺少云端大模型配置："
            + "、".join(missing)
            + f"。请复制 {ENV_PATH.name}.example 为 .env 并填写。"
        )


def require_xiaomi_login(settings: AppSettings) -> None:
    """校验小米登录信息（账号密码或 Cookie 至少一种）。"""
    if settings.mi_cookie:
        return
    if settings.mi_user and settings.mi_pass:
        return
    raise SystemExit(
        "缺少小米登录配置：请在 .env 中填写 MI_USER + MI_PASS，或填写 MI_COOKIE。"
    )


def get_speaker(settings: AppSettings, name: str) -> SpeakerConfig:
    """按名称取音箱配置，名称不区分大小写。"""
    key = name.strip().upper()
    if key not in settings.speakers:
        known = "、".join(settings.speakers)
        raise SystemExit(f"未知音箱「{name}」，可选：{known}")
    speaker = settings.speakers[key]
    if not speaker.did:
        raise SystemExit(
            f"未配置 {key}_DID。"
            "请先运行 python -m mi_ai.list_devices 获取 DID，再写入 .env。"
        )
    return speaker

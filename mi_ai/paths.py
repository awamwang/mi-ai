"""项目内持久化路径（token / 种子 / 鉴权告警）。"""

from __future__ import annotations

import os
from pathlib import Path

from mi_ai.settings import ROOT_DIR

DATA_DIR = ROOT_DIR / "data"
DEFAULT_TOKEN_PATH = DATA_DIR / "mi.token"
DEFAULT_SEED_PATH = DATA_DIR / "mi_pass_seed.json"
AUTH_REQUIRED_PATH = ROOT_DIR / "logs" / "AUTH_REQUIRED.txt"
LEGACY_TOKEN_PATH = Path.home() / ".mi.token"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_token_path() -> Path:
    """token 文件路径：优先环境变量，否则项目 data/mi.token。"""
    raw = os.getenv("XIAOGPT_MI_TOKEN_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_TOKEN_PATH


def get_seed_path() -> Path:
    raw = os.getenv("MI_AI_PASS_SEED_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_SEED_PATH

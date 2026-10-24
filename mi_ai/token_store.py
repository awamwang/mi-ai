"""安全 token 存储：失败时不删除 passToken，并维护备份与种子。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from mi_ai.paths import ensure_data_dir, get_seed_path, get_token_path

_LOGGER = logging.getLogger(__package__)

# 长期凭证字段：登录失败时必须保留
DURABLE_KEYS = ("deviceId", "userId", "passToken")


def extract_durable(token: dict[str, Any] | None) -> dict[str, Any]:
    if not token:
        return {}
    return {k: token[k] for k in DURABLE_KEYS if k in token and token[k]}


class SafeMiTokenStore:
    """替代 miservice.MiTokenStore：清空时不删文件，只剥离业务 sid。"""

    def __init__(self, token_path: str | Path | None = None):
        path = Path(token_path) if token_path else get_token_path()
        self.token_path = path
        self.backup_path = path.with_suffix(path.suffix + ".bak")

    def load_token(self) -> dict[str, Any] | None:
        for candidate in (self.token_path, self.backup_path):
            data = self._read_json(candidate)
            if data:
                if candidate != self.token_path:
                    _LOGGER.warning("从备份恢复 token：%s", candidate)
                    self.save_token(data)
                return data

        seeded = self._token_from_seed()
        if seeded:
            _LOGGER.warning("从 passToken 种子重建 token：%s", get_seed_path())
            self.save_token(seeded)
            return seeded
        return None

    def save_token(self, token: dict[str, Any] | None = None) -> None:
        """token 有值则写入；None 表示「失败清空」——仅剥离 sid，保留长期凭证。"""
        ensure_data_dir()
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

        if token:
            durable = extract_durable(token)
            if durable.get("passToken"):
                self._write_seed(durable)
            self._write_json(self.token_path, token)
            self._write_json(self.backup_path, token)
            return

        # 原版会 delete 文件；这里改为保留 durable，去掉 micoapi/xiaomiio 等 sid
        current = self._read_json(self.token_path) or self._read_json(self.backup_path) or {}
        durable = extract_durable(current) or self._token_from_seed() or {}
        if not durable:
            _LOGGER.warning("请求清空 token，但无 passToken 可保留，跳过删文件")
            return
        _LOGGER.warning("登录/鉴权失败：保留 passToken，仅清除业务 serviceToken")
        self._write_json(self.token_path, durable)
        self._write_json(self.backup_path, durable)

    def _token_from_seed(self) -> dict[str, Any] | None:
        seed = self._read_json(get_seed_path())
        if not seed:
            return None
        durable = extract_durable(seed)
        if not durable.get("passToken") or not durable.get("userId"):
            return None
        if "deviceId" not in durable:
            durable["deviceId"] = "A1B2C3D4E5F60718"
        return durable

    def _write_seed(self, durable: dict[str, Any]) -> None:
        path = get_seed_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(path, extract_durable(durable))

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            _LOGGER.exception("读取 token 失败：%s", path)
            return None

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            _LOGGER.exception("写入 token 失败：%s", path)


def migrate_legacy_token_if_needed() -> None:
    """若项目 token 不存在而用户目录有旧 ~/.mi.token，则迁移过来。"""
    target = get_token_path()
    if target.is_file():
        return
    legacy = Path(os.getenv("MI_AI_LEGACY_TOKEN", str(Path.home() / ".mi.token")))
    if not legacy.is_file():
        return
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("passToken"):
            store = SafeMiTokenStore(target)
            store.save_token(data)
            _LOGGER.info("已迁移旧 token：%s → %s", legacy, target)
    except Exception:
        _LOGGER.exception("迁移旧 token 失败")

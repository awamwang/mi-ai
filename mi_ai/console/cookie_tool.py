"""从浏览器整段 Cookie 提取长期凭证并写入 token（不写 MI_COOKIE）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mi_ai.token_store import SafeMiTokenStore

_DEFAULT_DEVICE_ID = "A1B2C3D4E5F60718"


@dataclass
class CookieExtractResult:
    ok: bool
    message: str
    user_id: str = ""
    pass_token_len: int = 0
    device_id: str = ""
    wrote_token: bool = False


def parse_cookie_string(raw: str) -> dict[str, str]:
    """解析 `a=1; b=2` 或换行分隔的 Cookie 文本。"""
    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        return {}
    # 允许用户粘贴 document.cookie 或 DevTools 多行
    text = text.replace("\n", ";")
    out: dict[str, str] = {}
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            out[key] = value
    return out


def _pick_device_id(cookies: dict[str, str]) -> str:
    device_id = (cookies.get("deviceId") or "").strip()
    if not device_id:
        return _DEFAULT_DEVICE_ID
    # 浏览器 wb_ 设备号不宜直接用于 mina STS，回退默认
    if device_id.startswith("wb_"):
        return _DEFAULT_DEVICE_ID
    if re.fullmatch(r"[A-Fa-f0-9]{16}", device_id):
        return device_id.upper()
    return _DEFAULT_DEVICE_ID


def apply_browser_cookie(raw: str) -> CookieExtractResult:
    """提取 userId/passToken，写入 mi.token 与种子。"""
    cookies = parse_cookie_string(raw)
    user_id = (cookies.get("userId") or "").strip()
    pass_token = (cookies.get("passToken") or "").strip()
    if not user_id or not pass_token:
        return CookieExtractResult(
            ok=False,
            message="未找到 userId 或 passToken，请确认粘贴的是 account.xiaomi.com 的 Cookie。",
        )

    device_id = _pick_device_id(cookies)
    token = {
        "deviceId": device_id,
        "userId": user_id,
        "passToken": pass_token,
    }
    # 清掉可能失效的业务 sid，强制后续用 passToken 换票
    store = SafeMiTokenStore()
    store.save_token(token)
    return CookieExtractResult(
        ok=True,
        message="已写入 data/mi.token 与 passToken 种子（未改 MI_COOKIE）。",
        user_id=user_id,
        pass_token_len=len(pass_token),
        device_id=device_id,
        wrote_token=True,
    )

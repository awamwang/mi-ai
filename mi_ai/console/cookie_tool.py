"""从浏览器整段 Cookie 提取长期凭证并写入 token（不写 MI_COOKIE）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

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
    found_keys: tuple[str, ...] = ()


def parse_cookie_string(raw: str) -> dict[str, str]:
    """解析整段 Cookie，尽量兼容常见粘贴格式。

    支持：
    - `a=1; b=2` / `Cookie: a=1; b=2`
    - 换行分隔的 `a=1`
    - DevTools 表格：`name\\tvalue` 或多列文本
    - Cookie 扩展导出的 JSON 数组 `[{name,value}, ...]`
    """
    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        return {}

    # Cookie 扩展 / 编辑器导出的 JSON
    if text[:1] in {"[", "{"}:
        parsed = _parse_cookie_json(text)
        if parsed:
            return parsed

    # 去掉可选的 Cookie: 请求头前缀
    if re.match(r"(?i)^cookie\s*:", text):
        text = re.sub(r"(?i)^cookie\s*:", "", text, count=1).strip()

    out: dict[str, str] = {}

    # DevTools Application 表格粘贴：每行 name \\t value \\t ...
    if "\t" in text and ("\n" in text or text.count("\t") >= 1):
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.lower().startswith("name\t"):
                continue
            cols = [c.strip() for c in line.split("\t") if c.strip()]
            if len(cols) >= 2 and re.fullmatch(r"[A-Za-z0-9_.-]+", cols[0]):
                # 跳过表头
                if cols[0].lower() in {"name", "key", "cookie"}:
                    continue
                out[cols[0]] = cols[1]
        if out.get("userId") or out.get("passToken"):
            return out

    # 标准 document.cookie / 整段 Cookie 头
    normalized = text.replace("\n", ";")
    for part in normalized.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            out[key] = value
    return out


def _parse_cookie_json(text: str) -> dict[str, str]:
    try:
        data: Any = json.loads(text)
    except Exception:
        return {}
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "cookies" in data and isinstance(data["cookies"], list):
            items = data["cookies"]
        else:
            # {"userId":"...","passToken":"..."} 或 name->value 映射
            return {
                str(k): str(v)
                for k, v in data.items()
                if isinstance(k, str) and v is not None and not isinstance(v, (dict, list))
            }
    else:
        return {}

    out: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("Name") or item.get("key")
        value = item.get("value") or item.get("Value")
        if name is None or value is None:
            continue
        out[str(name)] = str(value)
    return out


def _pick_device_id(cookies: dict[str, str], existing: dict | None = None) -> str:
    device_id = (cookies.get("deviceId") or "").strip()
    # 优先沿用本地已成功换票的 deviceId，避免浏览器 wb_ 设备号导致 mina STS 401
    existing_id = str((existing or {}).get("deviceId") or "").strip()
    if existing_id and re.fullmatch(r"[A-Fa-f0-9]{16}", existing_id):
        if not device_id or device_id.startswith("wb_"):
            return existing_id.upper()
    if not device_id:
        return _DEFAULT_DEVICE_ID
    # 浏览器 wb_ 设备号不宜直接用于 mina STS，回退默认
    if device_id.startswith("wb_"):
        return _DEFAULT_DEVICE_ID
    if re.fullmatch(r"[A-Fa-f0-9]{16}", device_id):
        return device_id.upper()
    return _DEFAULT_DEVICE_ID


def _cookie_get(cookies: dict[str, str], *names: str) -> str:
    """按候选名取值（大小写不敏感）。"""
    lower_map = {k.lower(): v for k, v in cookies.items()}
    for name in names:
        value = (lower_map.get(name.lower()) or "").strip()
        if value:
            return value
    return ""


def _stop_message(reason: str, *, found: tuple[str, ...] = ()) -> str:
    """解析失败统一文案：说明原因，并明确已停止后续步骤。"""
    parts = [reason.rstrip("。").rstrip()]
    if found:
        preview = "、".join(found[:12])
        more = f" 等 {len(found)} 个" if len(found) > 12 else f"（{len(found)} 个）"
        parts.append(f"当前识别到的字段：{preview}{more}")
    parts.append("已停止：未写入 token、未执行换票")
    return "。".join(parts) + "。"


def apply_browser_cookie(raw: str) -> CookieExtractResult:
    """从整段 Cookie 提取 userId/passToken，写入 mi.token 与种子。

    缺字段时只返回失败提示，绝不写盘、不暗示可继续换票。
    """
    if not (raw or "").strip():
        return CookieExtractResult(
            ok=False,
            message=_stop_message("请先粘贴 account.xiaomi.com 的整段 Cookie"),
        )

    cookies = parse_cookie_string(raw)
    found = tuple(sorted(cookies.keys()))
    if not found:
        return CookieExtractResult(
            ok=False,
            message=_stop_message(
                "无法从粘贴内容中解析出任何 Cookie 字段。"
                "请粘贴完整 Cookie 文本（支持 a=1; b=2、表格或 JSON 导出）"
            ),
        )

    user_id = _cookie_get(cookies, "userId", "user_id", "userid")
    pass_token = _cookie_get(cookies, "passToken", "pass_token", "passtoken")
    if not user_id or not pass_token:
        missing = []
        if not user_id:
            missing.append("userId")
        if not pass_token:
            missing.append("passToken")
        return CookieExtractResult(
            ok=False,
            message=_stop_message(
                f"整段 Cookie 解析成功，但缺少必需字段：{', '.join(missing)}。"
                "请确认来源是 account.xiaomi.com；"
                "若用页面 document.cookie，HttpOnly 的 passToken 不会出现，"
                "请改从 F12 → Application → Cookies 复制整表/整段",
                found=found,
            ),
            found_keys=found,
        )

    store = SafeMiTokenStore()
    existing = store.load_token() or {}
    # deviceId 仍用原始键；_pick_device_id 内部读 cookies.get("deviceId")
    if "deviceId" not in cookies:
        alt = _cookie_get(cookies, "deviceId", "device_id")
        if alt:
            cookies = {**cookies, "deviceId": alt}
    device_id = _pick_device_id(cookies, existing)
    token = {
        "deviceId": device_id,
        "userId": user_id,
        "passToken": pass_token,
    }
    # 清掉可能失效的业务 sid，强制后续用 passToken 换票
    store.save_token(token)
    return CookieExtractResult(
        ok=True,
        message=(
            f"已从整段 Cookie 提取 userId/passToken（共解析 {len(found)} 个字段），"
            f"写入 data/mi.token 与种子（未改 MI_COOKIE）；deviceId={device_id}。"
        ),
        user_id=user_id,
        pass_token_len=len(pass_token),
        device_id=device_id,
        wrote_token=True,
        found_keys=found,
    )

"""mi-ai 本机控制台 FastAPI 应用。"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mi_ai.auth import ensure_auth
from mi_ai.console.cookie_tool import apply_browser_cookie
from mi_ai.console.envfile import (
    WRITABLE_KEYS,
    parse_env_map,
    public_config_view,
    update_env_keys,
)
from mi_ai.console.status import collect_status
from mi_ai.paths import ROOT_DIR

_LOGGER = logging.getLogger(__package__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
SCRIPTS_DIR = ROOT_DIR / "scripts"

app = FastAPI(title="mi-ai console", docs_url=None, redoc_url=None)


class ConfigUpdateBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class CookieBody(BaseModel):
    cookie: str
    # 兼容旧前端；现已默认写入后自动换票并刷新登录状态
    login: bool = True


class ServiceBody(BaseModel):
    action: str  # start | stop | status


def create_app() -> FastAPI:
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    async def api_status() -> dict[str, Any]:
        return collect_status()

    @app.get("/api/config")
    async def api_config() -> dict[str, Any]:
        env_map = parse_env_map()
        return {
            "writable_keys": sorted(WRITABLE_KEYS),
            "values": public_config_view(env_map),
            "raw_present": {k: bool(env_map.get(k)) for k in sorted(WRITABLE_KEYS)},
        }

    @app.put("/api/config")
    async def api_config_put(body: ConfigUpdateBody) -> dict[str, Any]:
        # 脱敏占位不回写：前端对密钥若未改会提交原掩码或以空表示不改
        env_map = parse_env_map()
        updates: dict[str, str] = {}
        for key, value in body.values.items():
            if key not in WRITABLE_KEYS:
                continue
            if key in {"MI_PASS", "OPENAI_API_KEY", "CURSOR_API_KEY"}:
                # 全是 * 或与展示掩码相同 → 视为未修改
                if value == "" or set(value) <= {"*"}:
                    continue
                if value.startswith("*") and value.endswith(
                    (env_map.get(key) or "")[-4:]
                ):
                    continue
            updates[key] = value
        written = update_env_keys(updates)
        return {"ok": True, "written": written, "values": public_config_view()}

    @app.post("/api/cookie")
    async def api_cookie(body: CookieBody) -> dict[str, Any]:
        """解析整段 Cookie → 写入 → 自动强制换票探活 → 返回最新登录状态。

        缺字段时直接 400，绝不写盘、绝不换票。
        """
        result = apply_browser_cookie(body.cookie)
        if not result.ok:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": result.message,
                    "ok": False,
                    "wrote_token": False,
                    "auth": None,
                    "status": None,
                    "found_keys": list(result.found_keys),
                },
            )

        auth_payload: dict[str, Any] | None = None
        if body.login:
            try:
                auth = await ensure_auth(force_reticket=True)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("Cookie 写入后自动换票失败")
                status = collect_status()
                return {
                    "ok": False,
                    "message": f"{result.message}自动换票失败：{exc}",
                    "user_id": result.user_id,
                    "pass_token_len": result.pass_token_len,
                    "device_id": result.device_id,
                    "wrote_token": result.wrote_token,
                    "found_keys": list(result.found_keys),
                    "auth": {
                        "ok": False,
                        "message": str(exc),
                        "need_human": True,
                        "scope": _auth_scope_from_status(status),
                    },
                    "status": status,
                }
            status = collect_status()
            scope = _auth_scope_from_status(status)
            auth_payload = {
                "ok": auth.ok,
                "message": auth.message,
                "need_human": auth.need_human,
                "notification_url": auth.notification_url,
                "refreshed": auth.refreshed,
                "scope": scope,
                "has_micoapi": bool(status.get("auth", {}).get("has_micoapi")),
                "has_xiaomiio": bool(status.get("auth", {}).get("has_xiaomiio")),
            }
            return {
                "ok": auth.ok or scope == "partial",
                "message": result.message,
                "user_id": result.user_id,
                "pass_token_len": result.pass_token_len,
                "device_id": result.device_id,
                "wrote_token": result.wrote_token,
                "found_keys": list(result.found_keys),
                "auth": auth_payload,
                "status": status,
            }

        return {
            "ok": True,
            "message": result.message,
            "user_id": result.user_id,
            "pass_token_len": result.pass_token_len,
            "device_id": result.device_id,
            "wrote_token": result.wrote_token,
            "found_keys": list(result.found_keys),
            "auth": auth_payload,
            "status": collect_status(),
        }

    @app.post("/api/auth/refresh")
    async def api_auth_refresh() -> dict[str, Any]:
        """强制清除业务票后用 passToken/账号密码重新换票，再返回最新登录状态。"""
        try:
            auth = await ensure_auth(force_reticket=True)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("刷新登录状态失败")
            status = collect_status()
            return {
                "ok": False,
                "message": f"刷新登录状态失败：{exc}",
                "need_human": True,
                "notification_url": None,
                "refreshed": False,
                "scope": _auth_scope_from_status(status),
                "has_micoapi": bool(status.get("auth", {}).get("has_micoapi")),
                "has_xiaomiio": bool(status.get("auth", {}).get("has_xiaomiio")),
                "status": status,
            }
        status = collect_status()
        return {
            "ok": auth.ok,
            "message": auth.message,
            "need_human": auth.need_human,
            "notification_url": auth.notification_url,
            "refreshed": auth.refreshed,
            "scope": _auth_scope_from_status(status),
            "has_micoapi": bool(status.get("auth", {}).get("has_micoapi")),
            "has_xiaomiio": bool(status.get("auth", {}).get("has_xiaomiio")),
            "status": status,
        }

    @app.post("/api/service")
    async def api_service(body: ServiceBody) -> dict[str, Any]:
        action = body.action.strip().lower()
        if action not in {"start", "stop", "status"}:
            raise HTTPException(status_code=400, detail="action 仅支持 start/stop/status")
        script = {
            "start": SCRIPTS_DIR / "service-start.ps1",
            "stop": SCRIPTS_DIR / "service-stop.ps1",
            "status": SCRIPTS_DIR / "service-status.ps1",
        }[action]
        if not script.is_file():
            raise HTTPException(status_code=500, detail=f"缺少脚本：{script.name}")
        output, code = await asyncio.to_thread(_run_ps1, script)
        return {
            "ok": code == 0,
            "code": code,
            "output": output[-4000:],
            "status": collect_status() if action != "status" else collect_status(),
        }

    return app


def _auth_scope_from_status(status: dict[str, Any]) -> str:
    auth = status.get("auth") or {}
    has_micoapi = bool(auth.get("has_micoapi"))
    has_xiaomiio = bool(auth.get("has_xiaomiio"))
    if has_micoapi and has_xiaomiio:
        return "full"
    if has_micoapi:
        return "partial"
    return "none"


def _decode_subprocess_bytes(raw: bytes) -> str:
    """解码子进程输出。

    Windows 上 PowerShell 管道常为系统 ANSI（中文环境多为 GBK），
    不能只用 UTF-8，否则控制台网页会显示乱码。
    """
    if not raw:
        return ""
    candidates: list[str] = []
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            candidates.append(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    if not candidates:
        return raw.decode("utf-8", errors="replace")

    markers = ("服务", "状态", "运行中", "控制台", "项目", "日志", "启动", "停止")
    mojibake = ("鎺у埗", "锟斤拷", "Ã", "Â")

    def score(text: str) -> int:
        s = 0
        if "\ufffd" in text:
            s -= 100
        s += 10 * sum(1 for w in markers if w in text)
        s -= 30 * sum(1 for w in mojibake if w in text)
        return s

    return max(candidates, key=score)


def _run_ps1(script: Path) -> tuple[str, int]:
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            capture_output=True,
            timeout=120,
        )
        out = _decode_subprocess_bytes((proc.stdout or b"") + (proc.stderr or b""))
        return out.strip(), int(proc.returncode)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("执行脚本失败：%s", script)
        return str(exc), 1


async def _run_login_mina() -> dict[str, Any]:
    cmd = [
        str(ROOT_DIR / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "mi_ai.login_mina",
    ]
    if not Path(cmd[0]).is_file():
        cmd[0] = "python"

    def _run() -> tuple[str, int]:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            capture_output=True,
            timeout=120,
        )
        out = _decode_subprocess_bytes((proc.stdout or b"") + (proc.stderr or b""))
        return out.strip(), int(proc.returncode)

    output, code = await asyncio.to_thread(_run)
    # 以落盘 token 为准，区分完整成功 / 仅 micoapi
    has_micoapi = False
    has_xiaomiio = False
    try:
        from mi_ai.token_store import SafeMiTokenStore

        token = SafeMiTokenStore().load_token() or {}
        has_micoapi = "micoapi" in token
        has_xiaomiio = "xiaomiio" in token
    except Exception:  # noqa: BLE001
        pass
    scope = "full" if (has_micoapi and has_xiaomiio) else (
        "partial" if has_micoapi else "none"
    )
    if "LOGIN_SCOPE=full" in output:
        scope = "full"
    elif "LOGIN_SCOPE=partial" in output:
        scope = "partial"
    return {
        "ok": code == 0,
        "code": code,
        "output": output[-3000:],
        "scope": scope,
        "has_micoapi": has_micoapi,
        "has_xiaomiio": has_xiaomiio,
    }


# 模块导入即注册路由
create_app()

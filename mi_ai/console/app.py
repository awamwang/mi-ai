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
    login: bool = False


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
        result = apply_browser_cookie(body.cookie)
        payload: dict[str, Any] = {
            "ok": result.ok,
            "message": result.message,
            "user_id": result.user_id,
            "pass_token_len": result.pass_token_len,
            "device_id": result.device_id,
            "wrote_token": result.wrote_token,
            "login": None,
        }
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.message)
        if body.login:
            payload["login"] = await _run_login_mina()
        return payload

    @app.post("/api/auth/refresh")
    async def api_auth_refresh() -> dict[str, Any]:
        """用现有账号/passToken 重新换票，再返回最新登录状态。"""
        try:
            auth = await ensure_auth()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("刷新登录状态失败")
            return {
                "ok": False,
                "message": f"刷新登录状态失败：{exc}",
                "need_human": True,
                "notification_url": None,
                "refreshed": False,
                "status": collect_status(),
            }
        return {
            "ok": auth.ok,
            "message": auth.message,
            "need_human": auth.need_human,
            "notification_url": auth.notification_url,
            "refreshed": auth.refreshed,
            "status": collect_status(),
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
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
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
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return ((proc.stdout or "") + (proc.stderr or "")).strip(), int(proc.returncode)

    output, code = await asyncio.to_thread(_run)
    return {"ok": code == 0, "code": code, "output": output[-3000:]}


# 模块导入即注册路由
create_app()

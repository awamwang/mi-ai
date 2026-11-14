"""小米登录持久化：种子恢复、静默续期、探活与告警。"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aiohttp import ClientSession
from dotenv import load_dotenv

from mi_ai.auth_patch import apply_auth_patches
from mi_ai.paths import AUTH_REQUIRED_PATH, ROOT_DIR, get_token_path
from mi_ai.settings import ENV_PATH, load_settings, require_xiaomi_login
from mi_ai.token_store import SafeMiTokenStore, migrate_legacy_token_if_needed

_LOGGER = logging.getLogger(__package__)


@dataclass
class AuthStatus:
    ok: bool
    message: str
    need_human: bool = False
    notification_url: str | None = None
    refreshed: bool = False


def prepare_auth_env() -> Path:
    """应用补丁、迁移旧 token，并返回当前 token 路径。"""
    load_dotenv(ENV_PATH, override=True)
    apply_auth_patches()
    migrate_legacy_token_if_needed()
    token_path = get_token_path()
    os.environ["XIAOGPT_MI_TOKEN_PATH"] = str(token_path)
    return token_path


def clear_auth_required() -> None:
    if AUTH_REQUIRED_PATH.is_file():
        try:
            AUTH_REQUIRED_PATH.unlink()
        except OSError:
            pass


def write_auth_required(message: str, notification_url: str | None = None) -> Path:
    AUTH_REQUIRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"time={datetime.now().isoformat(timespec='seconds')}",
        f"message={message}",
    ]
    if notification_url:
        lines.append(f"notificationUrl={notification_url}")
        lines.append("")
        lines.append("请在浏览器打开上述链接完成验证，然后执行：")
        lines.append("  .\\.venv\\Scripts\\python.exe -m mi_ai.login_mina")
        lines.append("  .\\scripts\\service-stop.ps1")
        lines.append("  .\\scripts\\service-start.ps1")
    AUTH_REQUIRED_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return AUTH_REQUIRED_PATH


def notify_windows(title: str, body: str) -> None:
    """弹出 Windows 气泡通知（失败则静默忽略）。"""
    # 转义单引号，避免破坏 PowerShell 字符串
    safe_title = title.replace("'", "''")
    safe_body = body.replace("'", "''")[:180]
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Warning
$n.Visible = $true
$n.BalloonTipTitle = '{safe_title}'
$n.BalloonTipText = '{safe_body}'
$n.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
$n.ShowBalloonTip(10000)
Start-Sleep -Seconds 11
$n.Dispose()
"""
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        _LOGGER.debug("Windows 通知失败", exc_info=True)


async def _probe_login(user: str, password: str, token_path: Path) -> AuthStatus:
    from miservice import MiAccount, MiNAService

    store = SafeMiTokenStore(token_path)
    async with ClientSession() as session:
        account = MiAccount(session, user, password, store)
        if not account.token:
            account.token = store.load_token() or {"deviceId": "A1B2C3D4E5F60718"}

        # 先尝试用已有 passToken 刷新 micoapi
        ok = await account.login("micoapi")
        if not ok or not account.token or "micoapi" not in account.token:
            # 探测是否需要短信：走与 login_mina 相同的 probe
            if not account.token:
                account.token = store.load_token() or {"deviceId": "A1B2C3D4E5F60718"}
            probe = await account._serviceLogin("serviceLogin?sid=micoapi&_json=true")
            if probe.get("code") != 0:
                data = {
                    "_json": "true",
                    "qs": probe["qs"],
                    "sid": probe["sid"],
                    "_sign": probe["_sign"],
                    "callback": probe["callback"],
                    "user": user,
                    "hash": __import__("hashlib")
                    .md5(password.encode())
                    .hexdigest()
                    .upper(),
                }
                probe = await account._serviceLogin("serviceLoginAuth2", data)
            notify = (probe.get("notificationUrl") or "").strip() or None
            msg = (
                f"小米登录失败 code={probe.get('code')} "
                f"desc={probe.get('desc') or probe.get('description') or ''}"
            ).strip()
            # 仅在有验证链接或明确 securityStatus=16 时判定需人工
            need_human = bool(notify) or probe.get("securityStatus") == 16
            return AuthStatus(
                ok=False,
                message=msg or "小米登录失败（无法刷新 serviceToken）",
                need_human=need_human,
                notification_url=notify,
            )

        # 补齐 xiaomiio（L05C TTS）；失败不阻断 LX06（仅需 micoapi）
        ok_io = await account.login("xiaomiio")
        io_note = ""
        if not ok_io:
            io_note = "；警告：xiaomiio 未就绪（L05C command TTS 可能不可用，可再跑 login_mina）"

        # 轻量探活：列设备
        try:
            mina = MiNAService(account)
            devices = await mina.device_list()
            n = len(devices or [])
        except Exception as exc:  # noqa: BLE001
            return AuthStatus(
                ok=False,
                message=f"micoapi 票据已刷新但探活失败：{exc}",
                need_human=True,
            )

        return AuthStatus(
            ok=True,
            message=f"鉴权正常，可见设备 {n} 台；token={token_path}{io_note}",
            refreshed=True,
        )


def _human_recovery_hint(message: str, notification_url: str | None = None) -> str:
    """失败时补充控制台恢复路径（打开登录页 / Cookie 工具）。"""
    hints = [
        message.rstrip("。").rstrip(),
        "可在控制台「打开小米登录页」完成验证后，用 Cookie 工具粘贴 account.xiaomi.com 的 Cookie，再点「刷新登录状态」",
    ]
    if notification_url:
        hints.append(f"或直接打开验证链接：{notification_url}")
    return "。".join(hints) + "。"


def _mark_auth_failed(status: AuthStatus) -> AuthStatus:
    """写入失效标记并通知；仅在自动恢复也失败后调用。"""
    failed = AuthStatus(
        ok=False,
        message=_human_recovery_hint(status.message, status.notification_url),
        need_human=True,
        notification_url=status.notification_url,
        refreshed=status.refreshed,
    )
    path = write_auth_required(failed.message, failed.notification_url)
    notify_windows(
        "mi-ai 需要重新验证小米账号",
        failed.message[:120] + (f"；详见 {path.name}" if path else ""),
    )
    if failed.notification_url:
        (ROOT_DIR / "_auth_url.txt").write_text(
            failed.notification_url, encoding="utf-8"
        )
    return failed


async def _attempt_password_auth(
    user: str,
    password: str,
    token_path: Path,
    *,
    force_reticket: bool,
    strip_reason: str,
) -> AuthStatus:
    store = SafeMiTokenStore(token_path)
    if force_reticket:
        store.strip_business_sids(reason=strip_reason)
    return await _probe_login(user, password, token_path)


async def ensure_auth(*, force_reticket: bool = False) -> AuthStatus:
    """启动前或定期调用：探活；失败则强制换票自愈；仍失败才写告警。

    force_reticket=True：跳过软探活，直接清业务票换票（控制台「刷新登录状态」）。
    默认路径：软探活 → 失败则清 micoapi/xiaomiio 再换票 → 仍失败才标记登录失效。
    """
    token_path = prepare_auth_env()
    settings = load_settings()
    require_xiaomi_login(settings)
    store = SafeMiTokenStore(token_path)
    has_password = bool(settings.mi_user and settings.mi_pass)

    if not has_password:
        # 仅 Cookie 模式：无法用账号密码自愈
        token = store.load_token()
        if not force_reticket and token and token.get("micoapi"):
            clear_auth_required()
            return AuthStatus(ok=True, message="已有 micoapi token（Cookie 模式）")
        return _mark_auth_failed(
            AuthStatus(
                ok=False,
                message=(
                    "Cookie 模式无法静默换票，请配置 MI_USER/MI_PASS，"
                    "或粘贴浏览器 Cookie 后勾选立即换票"
                ),
                need_human=True,
            )
        )

    user = settings.mi_user
    password = settings.mi_pass

    if force_reticket:
        status = await _attempt_password_auth(
            user,
            password,
            token_path,
            force_reticket=True,
            strip_reason="控制台强制刷新：已清除业务 serviceToken，准备用 passToken 换票",
        )
        if status.ok:
            clear_auth_required()
            return status
        return _mark_auth_failed(status)

    # 1) 软探活（沿用现有业务票 / passToken 续期）
    status = await _attempt_password_auth(
        user,
        password,
        token_path,
        force_reticket=False,
        strip_reason="",
    )
    if status.ok:
        clear_auth_required()
        return status

    # 2) 失败后自动强制换票自愈（尚未标记失效）
    _LOGGER.warning(
        "鉴权探活失败，尝试清除业务票后自动恢复：%s",
        status.message[:200],
    )
    recovered = await _attempt_password_auth(
        user,
        password,
        token_path,
        force_reticket=True,
        strip_reason="自动恢复：已清除业务 serviceToken，准备用 passToken 换票",
    )
    if recovered.ok:
        clear_auth_required()
        recovered.message = f"鉴权已自动恢复（强制换票成功）。{recovered.message}"
        _LOGGER.info("%s", recovered.message)
        return recovered

    # 3) 仍失败：标记登录失效
    return _mark_auth_failed(recovered)


def main(argv: list[str] | None = None) -> None:
    """CLI：python -m mi_ai.auth_check 或 python -m mi_ai.auth"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    status = asyncio.run(ensure_auth())
    print(status.message)
    if status.notification_url:
        print(f"验证链接：{status.notification_url}")
        print(f"告警文件：{AUTH_REQUIRED_PATH}")
    if status.ok:
        raise SystemExit(0)
    raise SystemExit(2 if status.need_human else 1)


if __name__ == "__main__":
    main()

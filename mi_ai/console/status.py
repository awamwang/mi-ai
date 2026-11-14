"""汇总 watchdog / 设备进程 / 鉴权与配置摘要。"""

from __future__ import annotations

import json
import socket
from datetime import datetime
from pathlib import Path

from mi_ai.console.envfile import mask_secret, parse_env_map
from mi_ai.paths import AUTH_REQUIRED_PATH, ROOT_DIR, get_seed_path, get_token_path
from mi_ai.settings import SPEAKER_PROFILES, load_settings

TASK_NAME = "awam-mi-ai"


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, int(pid))
        if handle:
            kernel32.CloseHandle(handle)
            return True
        # 5 = ERROR_ACCESS_DENIED，进程仍存在
        return int(kernel32.GetLastError()) == 5
    except Exception:
        return Path(f"/proc/{pid}").exists()


def _read_pid(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip().splitlines()[0])
    except Exception:
        return 0


def _log_dir(env_map: dict[str, str]) -> Path:
    raw = (env_map.get("MI_AI_LOG_DIR") or "logs").strip() or "logs"
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _devices(env_map: dict[str, str]) -> list[str]:
    raw = env_map.get("MI_AI_DEVICES") or "LX06,L05C"
    parts = [p.strip().upper() for p in re_split(raw)]
    return [p for p in parts if p] or ["LX06", "L05C"]


def re_split(raw: str) -> list[str]:
    import re

    return re.split(r"[,;\s]+", raw)


def _port_listening(host: str, port: int) -> bool:
    """探测本机控制台端口是否已在监听。"""
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def collect_status() -> dict:
    """控制台概览数据。"""
    env_map = parse_env_map()
    settings = load_settings()
    log_dir = _log_dir(env_map)
    devices = _devices(env_map)

    wd_pid = _read_pid(log_dir / "watchdog.pid")
    watchdog = {
        "running": _pid_running(wd_pid),
        "pid": wd_pid if _pid_running(wd_pid) else 0,
    }

    device_rows = []
    for name in devices:
        pid = _read_pid(log_dir / f"{name}.pid")
        running = _pid_running(pid)
        speaker = settings.speakers.get(name)
        device_rows.append(
            {
                "name": name,
                "running": running,
                "pid": pid if running else 0,
                "did": speaker.did if speaker else env_map.get(f"{name}_DID", ""),
                "hardware": speaker.hardware
                if speaker
                else env_map.get(f"{name}_HARDWARE", name),
                "mute_xiaoai": speaker.mute_xiaoai if speaker else True,
                "stream": speaker.stream if speaker else name == "LX06",
                "use_command": speaker.use_command if speaker else name == "L05C",
                "log": str(log_dir / f"{name}-{datetime.now():%Y-%m-%d}.log"),
            }
        )

    # 未在 MI_AI_DEVICES 但在配置档里的音箱，也附带配置供查看
    extra = []
    for name in SPEAKER_PROFILES:
        if name in devices:
            continue
        speaker = settings.speakers[name]
        extra.append(
            {
                "name": name,
                "running": False,
                "pid": 0,
                "did": speaker.did,
                "hardware": speaker.hardware,
                "mute_xiaoai": speaker.mute_xiaoai,
                "stream": speaker.stream,
                "use_command": speaker.use_command,
                "log": "",
                "managed": False,
            }
        )
    for row in device_rows:
        row["managed"] = True

    token_path = get_token_path()
    seed_path = get_seed_path()
    token_keys: list[str] = []
    has_micoapi = False
    has_xiaomiio = False
    user_id = ""
    if token_path.is_file():
        try:
            data = json.loads(token_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                token_keys = sorted(data.keys())
                has_micoapi = "micoapi" in data
                has_xiaomiio = "xiaomiio" in data
                user_id = str(data.get("userId") or "")
        except Exception:
            pass

    auth_required = AUTH_REQUIRED_PATH.is_file()
    auth_message = ""
    notification_url = ""
    if auth_required:
        try:
            raw_auth = AUTH_REQUIRED_PATH.read_text(encoding="utf-8")
            auth_message = raw_auth[:400]
            for line in raw_auth.splitlines():
                if line.startswith("notificationUrl="):
                    notification_url = line.split("=", 1)[1].strip()
                    break
        except Exception:
            auth_message = "存在 AUTH_REQUIRED.txt"

    if auth_required:
        login_state = "need_human"
        login_label = "需要人工验证"
    elif has_micoapi and has_xiaomiio:
        login_state = "ok"
        login_label = "登录正常（micoapi + xiaomiio）"
    elif has_micoapi:
        login_state = "partial"
        login_label = "部分可用（micoapi 就绪，xiaomiio 缺失）"
    elif token_path.is_file():
        login_state = "token_only"
        login_label = "有长期凭证，待换票"
    else:
        login_state = "missing"
        login_label = "未登录"

    console_enabled = (env_map.get("MI_AI_CONSOLE") or "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    console_host = (env_map.get("MI_AI_CONSOLE_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        console_port = int((env_map.get("MI_AI_CONSOLE_PORT") or "18865").strip() or "18865")
    except ValueError:
        console_port = 18865
    console_pid = _read_pid(log_dir / "console.pid")
    console_running = _pid_running(console_pid)
    port_listening = _port_listening(console_host, console_port) if console_enabled else False

    return {
        "project_root": str(ROOT_DIR),
        "time": datetime.now().isoformat(timespec="seconds"),
        "task_name": TASK_NAME,
        "watchdog": watchdog,
        "console": {
            "enabled": console_enabled,
            "running": console_running,
            "pid": console_pid if console_running else 0,
            "host": console_host,
            "port": console_port,
            "url": f"http://{console_host}:{console_port}/",
            "port_listening": port_listening,
            "registered": console_enabled,
        },
        "devices": device_rows + extra,
        "auth": {
            "token_path": str(token_path),
            "token_exists": token_path.is_file(),
            "seed_exists": seed_path.is_file(),
            "token_keys": token_keys,
            "has_micoapi": has_micoapi,
            "has_xiaomiio": has_xiaomiio,
            "user_id_masked": mask_secret(user_id, keep=2) if user_id else "",
            "auth_required": auth_required,
            "auth_message": auth_message,
            "notification_url": notification_url,
            "login_page_url": "https://account.xiaomi.com",
            "login_state": login_state,
            "login_label": login_label,
            "mi_user_masked": mask_secret(settings.mi_user, keep=3)
            if settings.mi_user
            else "",
        },
        "dialog": {
            "keywords": list(settings.keywords),
            "prompt": settings.prompt,
            "start_conversation": settings.start_conversation,
            "end_conversation": settings.end_conversation,
            "openai_api_base": settings.openai_api_base,
            "openai_model": settings.openai_model,
            "openai_api_key_masked": mask_secret(settings.openai_api_key),
        },
    }

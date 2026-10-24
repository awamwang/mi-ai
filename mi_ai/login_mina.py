"""使用 .env 中的 MI_USER / MI_PASS 登录小米并列出音箱。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from aiohttp import ClientSession
from dotenv import load_dotenv

from mi_ai.auth import clear_auth_required, prepare_auth_env
from mi_ai.paths import get_token_path
from mi_ai.settings import ENV_PATH, load_settings, require_xiaomi_login
from mi_ai.token_store import SafeMiTokenStore


async def _login_and_list(user: str, password: str) -> int:
    from miservice import MiAccount, MiNAService

    token_path = get_token_path()
    store = SafeMiTokenStore(token_path)
    async with ClientSession() as session:
        account = MiAccount(session, user, password, store)

        # 先看登录响应，便于定位 70016 / 验证码
        if not account.token:
            account.token = {"deviceId": "A1B2C3D4E5F60718"}
        probe = await account._serviceLogin("serviceLogin?sid=micoapi&_json=true")
        if probe.get("code") != 0:
            # 走账号密码二次认证
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

        if probe.get("code") != 0 or "userId" not in probe:
            print("小米登录未完成。结果（已脱敏）：")
            safe = {
                k: probe.get(k)
                for k in (
                    "code",
                    "desc",
                    "description",
                    "result",
                    "securityStatus",
                    "captchaUrl",
                )
                if k in probe
            }
            print(json.dumps(safe, ensure_ascii=False, indent=2))
            notify = probe.get("notificationUrl")
            if notify:
                auth_file = Path(__file__).resolve().parent.parent / "_auth_url.txt"
                auth_file.write_text(notify, encoding="utf-8")
                print("\n需要身份验证。请在浏览器打开下面链接，完成短信/邮箱验证：")
                print(notify)
                print(f"\n（链接已写入 {auth_file}）")
                print("验证完成后再运行：python -m mi_ai.login_mina")
            else:
                print(
                    "\n无验证链接时，可改用 Cookie：\n"
                    "1. Chrome 登录 https://account.xiaomi.com\n"
                    "2. F12 → Application → Cookies，复制 userId 与 passToken\n"
                    "3. 写入 .env：MI_COOKIE=userId=...; passToken=...\n"
                )
            return 1

        # 正常完整登录以写入 token（含 passToken 种子）
        account.token = {"deviceId": account.token.get("deviceId", "A1B2C3D4E5F60718")}
        ok = await account.login("micoapi")
        if not ok:
            print("login() 返回失败，请改用 Cookie 方式。")
            return 1

        # L05C 等机型走 MiIO TTS，需要额外登录 xiaomiio
        ok_io = await account.login("xiaomiio")
        if not ok_io:
            print("警告：xiaomiio 登录失败，L05C 的 command TTS 可能不可用。")
        else:
            print("micoapi + xiaomiio 均已登录。")

        clear_auth_required()
        print(f"登录成功，token 已写入：{token_path}")
        print(f"passToken 种子已保存，供失败后静默恢复。")
        mina = MiNAService(account)
        devices = await mina.device_list()
        if not devices:
            print("未找到音箱设备。")
            return 0

        print(f"共 {len(devices)} 台设备：\n")
        print(f"{'名称':<24} {'hardware':<12} {'miotDID':<24} deviceID")
        print("-" * 88)
        for d in devices:
            name = str(d.get("name") or "-")
            hardware = str(d.get("hardware") or "-")
            did = str(d.get("miotDID") or "")
            device_id = str(d.get("deviceID") or "")
            print(f"{name:<24} {hardware:<12} {did:<24} {device_id}")

        print("\n请把 miotDID 写入 .env 的 LX06_DID / L05C_DID。")
        return 0


def main() -> None:
    load_dotenv(ENV_PATH, override=True)
    prepare_auth_env()
    settings = load_settings()
    require_xiaomi_login(settings)
    if not (settings.mi_user and settings.mi_pass):
        raise SystemExit("需要 MI_USER 与 MI_PASS。")

    os.environ["MI_USER"] = settings.mi_user
    os.environ["MI_PASS"] = settings.mi_pass
    print(f"使用账号：{settings.mi_user[:3]}***（来自 .env）")
    print(f"token 路径：{get_token_path()}")
    code = asyncio.run(_login_and_list(settings.mi_user, settings.mi_pass))
    raise SystemExit(code)


if __name__ == "__main__":
    main()

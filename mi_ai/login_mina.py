"""使用 .env 中的 MI_USER / MI_PASS 登录小米并列出音箱。"""

from __future__ import annotations

import asyncio
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

        # 直接走补丁后的 login：避免先 probe 再 login 重复换票、误耗一次性 STS location
        if not account.token:
            account.token = store.load_token() or {"deviceId": "A1B2C3D4E5F60718"}
        if "deviceId" not in account.token:
            account.token["deviceId"] = "A1B2C3D4E5F60718"
        # 清掉可能过期的业务 sid，强制按 passToken 重新换票
        for sid in ("micoapi", "xiaomiio"):
            account.token.pop(sid, None)
        if account.token_store:
            account.token_store.save_token(account.token)

        ok = await account.login("micoapi")
        if not ok or "micoapi" not in (account.token or {}):
            print("micoapi 登录失败（常见：需短信验证，或 serviceToken 未下发）。")
            print("可打开 https://account.xiaomi.com 完成验证后重试；")
            print(
                "或用控制台 Cookie 工具粘贴 account.xiaomi.com 的整段 Cookie"
                "（程序会自动提取 userId/passToken；勿只用 document.cookie）。"
            )
            auth_file = Path(__file__).resolve().parent.parent / "_auth_url.txt"
            if auth_file.is_file():
                print(f"若已生成验证链接，见：{auth_file}")
            return 1

        # L05C 等机型走 MiIO TTS，需要额外登录 xiaomiio
        ok_io = await account.login("xiaomiio")
        if not ok_io:
            print("警告：xiaomiio 登录失败，L05C 的 command TTS 可能不可用。")
            print("（micoapi 仍保留，LX06 一般可继续用）")
            print("LOGIN_SCOPE=partial")
        else:
            print("micoapi + xiaomiio 均已登录。")
            print("LOGIN_SCOPE=full")

        if "micoapi" not in account.token:
            print("内部错误：micoapi 票据在 xiaomiio 失败后丢失，请重试。")
            return 1

        clear_auth_required()
        if ok_io:
            print(f"登录成功（完整），token 已写入：{token_path}")
        else:
            print(f"登录部分成功（仅 micoapi），token 已写入：{token_path}")
        print("passToken 种子已保存，供失败后静默恢复。")
        mina = MiNAService(account)
        try:
            devices = await mina.device_list()
        except Exception as exc:  # noqa: BLE001
            print(f"列出设备失败：{exc}")
            print("token 已写入；可稍后重试 python -m mi_ai.login_mina 或直接启动服务。")
            return 1
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

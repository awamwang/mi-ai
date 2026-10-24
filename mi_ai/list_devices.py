"""列出当前小米账号下的音箱设备与 DID。"""

from __future__ import annotations

import asyncio
import os
import sys

from mi_ai.auth import prepare_auth_env
from mi_ai.ensure_deps import patch_xiaogpt_bots
from mi_ai.paths import get_token_path
from mi_ai.settings import load_settings, require_xiaomi_login
from mi_ai.token_store import SafeMiTokenStore


async def _list_via_miservice(user: str, password: str) -> None:
    """使用 miservice 列出设备。"""
    from aiohttp import ClientSession
    from miservice import MiAccount, MiNAService

    store = SafeMiTokenStore(get_token_path())
    async with ClientSession() as session:
        account = MiAccount(session, user, password, store)
        await account.login("micoapi")
        mina = MiNAService(account)
        devices = await mina.device_list()
        if not devices:
            print("未找到任何音箱设备。请确认音箱已在米家绑定且与账号同一网络登录过。")
            return

        print(f"共 {len(devices)} 台设备：\n")
        print(f"{'名称':<24} {'hardware':<12} {'miotDID(填.env)':<24} deviceID")
        print("-" * 88)
        for d in devices:
            name = str(d.get("name") or d.get("alias") or "-")
            hardware = str(d.get("hardware") or "-")
            # xiaogpt / MI_DID 使用 miotDID
            did = str(d.get("miotDID") or "")
            device_id = str(d.get("deviceID") or "")
            print(f"{name:<24} {hardware:<12} {did:<24} {device_id}")

        print("\n请把对应音箱的 miotDID 填入 .env：")
        print("  LX06_DID=<小爱音箱 Pro 的 miotDID>")
        print("  L05C_DID=<Play 增强版 的 miotDID>")
        print("\n若 hardware 显示为 LX06 / L05C，可按下面对号入座。")
        print("原始 JSON（排查用）：")
        for d in devices:
            print(d)


def main() -> None:
    prepare_auth_env()
    patch_xiaogpt_bots()
    settings = load_settings()
    require_xiaomi_login(settings)

    if settings.mi_cookie:
        print(
            "当前配置了 MI_COOKIE。"
            "列出设备仍建议使用 MI_USER + MI_PASS；"
            "若账号密码已填将优先用账号登录。"
        )

    if not (settings.mi_user and settings.mi_pass):
        raise SystemExit("列出设备需要 MI_USER 与 MI_PASS，请先写入 .env。")

    # 同步到环境变量，兼容 miservice / xiaogpt
    os.environ["MI_USER"] = settings.mi_user
    os.environ["MI_PASS"] = settings.mi_pass

    try:
        asyncio.run(_list_via_miservice(settings.mi_user, settings.mi_pass))
    except Exception as exc:  # noqa: BLE001 — 给用户可读错误
        print(f"列出设备失败：{exc}", file=sys.stderr)
        print(
            "\n可尝试：\n"
            "  1. 确认账号密码正确，并完成本机短信验证（首次）\n"
            "  2. 更换网络后再试\n"
            "  3. 手动执行：miservice mina / miservice list",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

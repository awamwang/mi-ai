"""启动指定音箱的 xiaogpt 桥接服务。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mi_ai.ensure_deps import patch_xiaogpt_bots
from mi_ai.settings import (
    get_speaker,
    load_settings,
    require_cloud_llm,
    require_xiaomi_login,
)


def build_config(device: str):
    """根据 .env 与音箱配置构建 xiaogpt Config。"""
    from xiaogpt.config import Config

    settings = load_settings()
    require_xiaomi_login(settings)
    require_cloud_llm(settings)
    speaker = get_speaker(settings, device)

    # xiaogpt / miservice 从环境变量读取 DID 与账号
    os.environ["MI_DID"] = speaker.did
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.mi_user:
        os.environ["MI_USER"] = settings.mi_user
    if settings.mi_pass:
        os.environ["MI_PASS"] = settings.mi_pass

    api_base = settings.openai_api_base.rstrip("/")
    # 常见误写：末尾带了 /chat/completions
    if api_base.endswith("/chat/completions"):
        api_base = api_base[: -len("/chat/completions")]

    return Config(
        hardware=speaker.hardware,
        account=settings.mi_user,
        password=settings.mi_pass,
        openai_key=settings.openai_api_key,
        mi_did=speaker.did,
        cookie=settings.mi_cookie,
        api_base=api_base,
        bot="chatgptapi",
        keyword=settings.keywords,
        prompt=settings.prompt,
        mute_xiaoai=speaker.mute_xiaoai,
        use_command=speaker.use_command,
        stream=speaker.stream,
        start_conversation=settings.start_conversation,
        end_conversation=settings.end_conversation,
        proxy=settings.http_proxy or None,
        verbose=settings.verbose,
        gpt_options={"model": settings.openai_model} if settings.openai_model else {},
        tts="mi",
    )


async def _ensure_xiaomiio_if_needed(config) -> None:
    """use_command 依赖 MiIO，启动前确保 xiaomiio token 存在。"""
    if not config.use_command:
        return
    import json
    from pathlib import Path

    from aiohttp import ClientSession
    from miservice import MiAccount

    token_path = os.getenv("XIAOGPT_MI_TOKEN_PATH") or str(Path.home() / ".mi.token")
    token_file = Path(token_path)
    if token_file.is_file():
        data = json.loads(token_file.read_text(encoding="utf-8"))
        if "xiaomiio" in data:
            return

    if not (config.account and config.password):
        print("警告：需要 xiaomiio 登录但缺少账号密码，L05C 播报可能失败。")
        return

    async with ClientSession() as session:
        account = MiAccount(session, config.account, config.password, token_path)
        ok = await account.login("xiaomiio")
        if ok:
            print("已补齐 xiaomiio 登录。")
        else:
            print("警告：xiaomiio 登录失败，请先运行 python -m mi_ai.login_mina")


async def _run_forever(config) -> None:
    from xiaogpt.xiaogpt import MiGPT

    await _ensure_xiaomiio_if_needed(config)
    miboy = MiGPT(config)
    try:
        await miboy.run_forever()
    finally:
        await miboy.close()


def _fix_stdio_encoding() -> None:
    """避免 Windows 控制台 GBK 无法打印模型回复中的特殊字符。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> None:
    _fix_stdio_encoding()
    # 必须在导入 xiaogpt.bot 之前精简 bot 入口
    patch_xiaogpt_bots()

    parser = argparse.ArgumentParser(
        description="启动小米音箱 ↔ 云端大模型桥接（xiaogpt）",
    )
    parser.add_argument(
        "device",
        choices=["LX06", "L05C", "lx06", "l05c"],
        help="要启动的音箱：LX06（Pro）或 L05C（Play 增强版）",
    )
    args = parser.parse_args(argv)
    device = args.device.upper()

    try:
        config = build_config(device)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"配置错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        f"启动 {device} | hardware={config.hardware} | did={config.mi_did} | "
        f"stream={config.stream} | use_command={config.use_command} | "
        f"mute={config.mute_xiaoai}"
    )
    print(
        f"模型：base={config.api_base} model={config.gpt_options.get('model', '')}"
    )
    print(f"触发词：{', '.join(config.keyword)}")
    print("对音箱说：小爱同学，帮我…… / 请问……")
    print("按 Ctrl+C 结束\n")

    try:
        asyncio.run(_run_forever(config))
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()

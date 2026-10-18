"""将已安装的 xiaogpt 限制为仅启用 OpenAI 兼容 bot，避免拉取 langchain/gemini 等重依赖。"""

from __future__ import annotations

from pathlib import Path

PATCHED_BOT_INIT = '''\
from __future__ import annotations

from xiaogpt.bot.base_bot import BaseBot
from xiaogpt.bot.chatgptapi_bot import ChatGPTBot
from xiaogpt.config import Config

BOTS: dict[str, type[BaseBot]] = {
    "chatgptapi": ChatGPTBot,
}


def get_bot(config: Config) -> BaseBot:
    try:
        return BOTS[config.bot].from_config(config)
    except KeyError:
        raise ValueError(f"Unsupported bot {config.bot}, must be one of {list(BOTS)}")


__all__ = [
    "ChatGPTBot",
    "get_bot",
]
'''


def patch_xiaogpt_bots() -> Path:
    """覆盖 xiaogpt.bot.__init__，仅保留 chatgptapi。"""
    import xiaogpt

    bot_init = Path(xiaogpt.__file__).resolve().parent / "bot" / "__init__.py"
    current = bot_init.read_text(encoding="utf-8")
    if "langchain_bot" not in current and '"chatgptapi": ChatGPTBot' in current:
        return bot_init
    bot_init.write_text(PATCHED_BOT_INIT, encoding="utf-8")
    return bot_init


if __name__ == "__main__":
    path = patch_xiaogpt_bots()
    print(f"已精简 xiaogpt bot 入口：{path}")

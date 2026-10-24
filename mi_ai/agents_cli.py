"""Agent 注册表管理：列出、试路由、绑定命名聊天。"""

from __future__ import annotations

import argparse
import json

from mi_ai.agents.bindings import (
    BINDINGS_PATH,
    get_last_agent_id,
    list_chats,
    set_chat_id,
)
from mi_ai.agents.config import load_agent_registry
from mi_ai.agents.router import route_query


def _cmd_list(_: argparse.Namespace) -> None:
    registry = load_agent_registry()
    print(f"配置：{registry.source_path}")
    print(f"默认：{registry.default_id}")
    print(f"CURSOR_API_KEY：{'已配置' if registry.cursor_api_key else '未配置'}")
    print()
    for agent in registry.agents.values():
        flag = "ON " if agent.enabled else "OFF"
        print(f"[{flag}] {agent.id}  type={agent.type}")
        print(f"       aliases={', '.join(agent.aliases)}")
        if agent.type.startswith("cursor"):
            opt = f"  optimize_for={agent.optimize_for}" if agent.optimize_for else ""
            print(
                f"       resume_policy={agent.resume_policy}  "
                f"model={agent.model}{opt}"
            )
            if agent.cwd:
                print(f"       cwd={agent.cwd}")
            yaml_chats = agent.chats
            bound = list_chats(agent.id)
            last = get_last_agent_id(agent.id)
            if yaml_chats:
                print(f"       yaml chats={yaml_chats}")
            if bound:
                print(f"       bound chats={bound}")
            if last:
                print(f"       last_agent_id={last}")
        print()


def _cmd_route(args: argparse.Namespace) -> None:
    registry = load_agent_registry()
    decision = route_query(args.text, registry)
    print(
        json.dumps(
            {
                "agent": decision.agent.id,
                "type": decision.agent.type,
                "enabled": decision.agent.enabled,
                "chat_name": decision.chat_name,
                "resume_agent_id": decision.resume_agent_id,
                "matched_alias": decision.matched_alias,
                "explicit": decision.explicit,
                "query": decision.query,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _cmd_bind(args: argparse.Namespace) -> None:
    path = set_chat_id(args.agent, args.chat, args.agent_id)
    print(f"已绑定 {args.agent}/{args.chat} → {args.agent_id}")
    print(f"写入：{path}")


def _cmd_chats(args: argparse.Namespace) -> None:
    registry = load_agent_registry()
    agent = registry.get(args.agent)
    if agent is None:
        raise SystemExit(f"未知 Agent：{args.agent}")
    print(f"Agent：{args.agent}")
    print(f"yaml chats：{agent.chats or '{}'}")
    print(f"bound chats：{list_chats(args.agent) or '{}'}")
    print(f"last：{get_last_agent_id(args.agent) or '-'}")
    print(f"bindings 文件：{BINDINGS_PATH}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="mi-ai Agent 路由管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出注册表")
    p_list.set_defaults(func=_cmd_list)

    p_route = sub.add_parser("route", help="试跑口令路由（不真正调用）")
    p_route.add_argument("text", help="完整用户问题文本")
    p_route.set_defaults(func=_cmd_route)

    p_bind = sub.add_parser("bind", help="绑定命名聊天到 Cursor agent_id")
    p_bind.add_argument("agent", help="Agent id，如 cursor")
    p_bind.add_argument("chat", help="聊天名，如 登录")
    p_bind.add_argument("agent_id", help="Cursor agent_id（agent-… 或 bc-…）")
    p_bind.set_defaults(func=_cmd_bind)

    p_chats = sub.add_parser("chats", help="查看某 Agent 的命名聊天")
    p_chats.add_argument("agent", help="Agent id")
    p_chats.set_defaults(func=_cmd_chats)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

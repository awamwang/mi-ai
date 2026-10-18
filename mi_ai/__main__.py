"""支持 python -m mi_ai <子命令>。"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "用法：\n"
            "  python -m mi_ai list          # 列出音箱 DID\n"
            "  python -m mi_ai run LX06      # 启动小爱音箱 Pro\n"
            "  python -m mi_ai run L05C      # 启动 Play 增强版\n"
        )
        raise SystemExit(1)

    cmd = sys.argv[1].lower()
    rest = sys.argv[2:]

    if cmd in {"list", "list-devices", "devices"}:
        from mi_ai.list_devices import main as list_main

        list_main()
    elif cmd == "run":
        from mi_ai.run import main as run_main

        if not rest:
            print("请指定音箱：python -m mi_ai run LX06 或 L05C")
            raise SystemExit(1)
        run_main(rest)
    else:
        print(f"未知命令：{cmd}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

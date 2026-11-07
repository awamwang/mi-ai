"""启动本机控制台：python -m mi_ai.console"""

from __future__ import annotations

import argparse
import webbrowser

from mi_ai.console import DEFAULT_HOST, DEFAULT_PORT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="启动 mi-ai 本机控制台")
    parser.add_argument("--host", default=DEFAULT_HOST, help="默认仅本机 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="默认 18865")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="不自动打开浏览器",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "缺少依赖：请先 pip install fastapi uvicorn\n"
            "或 .\\.venv\\Scripts\\python.exe -m pip install fastapi uvicorn"
        ) from exc

    from mi_ai.console.app import app

    url = f"http://{args.host}:{args.port}/"
    print(f"mi-ai 控制台：{url}")
    if not args.no_open and args.host in {"127.0.0.1", "localhost"}:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

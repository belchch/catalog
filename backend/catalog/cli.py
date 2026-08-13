from __future__ import annotations

import argparse
import os
import threading
import webbrowser

import uvicorn


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="catalog")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("CATALOG_PORT", os.getenv("PORT", "8000"))),
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    host = args.host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"

    url = f"http://{host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run("catalog.main:app", host=host, port=args.port)


if __name__ == "__main__":
    main()

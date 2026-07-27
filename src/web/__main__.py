"""Run with: python -m src.web"""

from __future__ import annotations

import uvicorn

from src.web.deps import resolve_bind_host, resolve_bind_port


def main() -> None:
    host = resolve_bind_host()
    port = resolve_bind_port()
    uvicorn.run("src.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

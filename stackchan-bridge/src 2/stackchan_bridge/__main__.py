from __future__ import annotations

import uvicorn

from stackchan_bridge.server.app import create_app
from stackchan_bridge.server.config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        create_app(settings=settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()


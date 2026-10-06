"""Entry point: `python -m reelhaven` or the `reelhaven` script."""

import logging

import uvicorn

from reelhaven import __version__
from reelhaven.app import create_app
from reelhaven.config import get_settings
from reelhaven.logsetup import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        settings.log_dir,
        settings.log_file_max_bytes,
        settings.log_file_backups,
    )
    logging.getLogger("reelhaven").info(
        "ReelHaven %s starting",
        __version__,
        extra={"config_dir": str(settings.config_dir), "port": settings.port},
    )
    uvicorn.run(
        create_app(web_dir=settings.web_dir),
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_config=None,  # keep the JSON logging configured above
        proxy_headers=False,  # client IPs come from the socket (SECURITY.md)
        server_header=False,
    )


if __name__ == "__main__":
    main()

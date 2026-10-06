"""Entry point: `python -m reelhaven` or the `reelhaven` script."""

import uvicorn

from reelhaven.app import create_app


def main() -> None:
    uvicorn.run(create_app(), host="0.0.0.0", port=7171, access_log=False)  # noqa: S104


if __name__ == "__main__":
    main()

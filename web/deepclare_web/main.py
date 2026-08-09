"""Entry point: serve the site. Binds $PORT on Cloud Run, WEB_PORT locally."""

import os

import uvicorn

from deepclare_web.app import create_app


def main() -> None:
    port = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8090")
    uvicorn.run(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

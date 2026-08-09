"""FastAPI app factory for the public website.

Static informational pages only — no business logic, no imports from other components.
"""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deepclare_web.config import SiteConfig
from deepclare_web.logging_config import configure_logging

_PACKAGE_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def _static_version() -> str:
    """Content hash of the mutable static assets — cache-busts ?v= URLs on change."""
    digest = hashlib.md5()
    for name in ("styles.css", "demo.js", "site.js"):
        path = _PACKAGE_DIR / "static" / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


def create_app(config: SiteConfig | None = None) -> FastAPI:
    configure_logging()
    site = config or SiteConfig.from_env()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=_PACKAGE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=_PACKAGE_DIR / "templates")
    templates.env.globals["current_year"] = datetime.now(UTC).year
    templates.env.globals["static_v"] = _static_version()

    def render(request: Request, name: str, **extra: object) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request, name=name, context={"site": site, **extra}
        )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return render(request, "index.html")

    @app.get("/terms", response_class=HTMLResponse)
    def terms(request: Request) -> HTMLResponse:
        return render(request, "terms.html")

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy(request: Request) -> HTMLResponse:
        return render(request, "privacy.html")

    @app.get("/refund", response_class=HTMLResponse)
    def refund(request: Request) -> HTMLResponse:
        return render(request, "refund.html")

    @app.get("/contact", response_class=HTMLResponse)
    def contact(request: Request) -> HTMLResponse:
        return render(request, "contact.html")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # An Armenian 404 page instead of FastAPI's English JSON default: the bank
    # reviewer must never see anything that looks unfinished or non-Armenian.
    def not_found(request: Request, exc: Exception) -> HTMLResponse:
        response = render(request, "404.html")
        response.status_code = 404
        return response

    app.add_exception_handler(404, not_found)

    return app

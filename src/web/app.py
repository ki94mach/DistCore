"""FastAPI application factory for the DistCore web MVP."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web.deps import (
    close_runtime_connections,
    get_job_store,
    resolve_db_config_path,
    resolve_jobs_root,
)
from src.web.errors import register_exception_handlers
from src.web.routes import data, health, meta, optimizations

_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))
logger = logging.getLogger("src.web")


def configure_logging() -> None:
    """Ensure INFO logs go to stdout for service managers."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logging.getLogger("src.web").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    jobs_root = resolve_jobs_root()
    config_path = resolve_db_config_path()
    logger.info(
        "Starting DistCore web MVP (jobs_dir=%s, db_config=%s)",
        jobs_root,
        config_path or "default db.yml",
    )
    stale = get_job_store().mark_stale_on_startup()
    if stale:
        logger.warning("Marked %s leftover job(s) as failed after process restart", stale)
    yield
    close_runtime_connections()
    logger.info("Shutting down DistCore web MVP")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="DistCore Web MVP",
        description="One-user refresh → optimize → Excel download UI/API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(data.router)
    app.include_router(meta.router)
    app.include_router(optimizations.router)

    static_dir = _PACKAGE_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(request, "index.html")

    return app


app = create_app()

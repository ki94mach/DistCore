"""FastAPI application factory for the DistCore web MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web.deps import get_job_store
from src.web.errors import register_exception_handlers
from src.web.routes import data, health, meta, optimizations

_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_job_store().mark_stale_on_startup()
    yield


def create_app() -> FastAPI:
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

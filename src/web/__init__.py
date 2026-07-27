"""One-user DistCore web MVP (FastAPI)."""

__all__ = ["create_app"]


def create_app():
    from src.web.app import create_app as _create_app

    return _create_app()

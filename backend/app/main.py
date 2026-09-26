from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, catalog, platform, processes, suppliers
from app.config import get_settings
from app.core.errors import DomainError

log = logging.getLogger("app")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.expose_docs and not settings.is_production
    app = FastAPI(
        title="Buq'ata Digital Processes API",
        version="0.5.0",
        docs_url="/api/v1/docs" if docs else None,
        openapi_url="/api/v1/openapi.json" if docs else None,
        redoc_url=None,
    )
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error",
                                                                "message": "Invalid request", "details": {"errors": errors}}})

    for module in (catalog, auth, suppliers, processes, platform):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()

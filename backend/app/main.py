"""FastAPI application entrypoint and HTTP route registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.routes.auth import router as auth_router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application used by the API Container App.

    Args:
        settings: Optional settings override used in tests.

    Returns:
        FastAPI: Configured application instance with baseline routes and security middleware.
    """
    runtime_settings = settings or get_settings()
    expose_docs = not runtime_settings.is_production

    application = FastAPI(
        title="AI Job Matcher & CV Analyzer",
        description="UK job matching with CV analysis and async Analysis Runs.",
        version="0.1.0",
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    application.state.settings = runtime_settings
    application.add_middleware(SecurityHeadersMiddleware, settings=runtime_settings)
    register_exception_handlers(application, runtime_settings)
    application.include_router(auth_router)

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        """Report whether the API process is running."""
        return {"status": "ok"}

    return application


app = create_app()

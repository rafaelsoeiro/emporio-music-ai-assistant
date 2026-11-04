from fastapi import FastAPI

from app.api.router import api_router
from app.api.routes.chat import router as chat_router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
    )

    application.include_router(api_router, prefix=settings.api_v1_prefix)
    application.include_router(chat_router)

    @application.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs"}

    return application


app = create_app()

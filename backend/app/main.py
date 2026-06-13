from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import get_chat_service, router
from backend.app.core.config import get_settings
from backend.app.core.database import close_database_pools
from backend.app.services.chat_service import shutdown_chat_workers


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_chat_service().warm_up()
    except Exception:
        logger.exception("Chat service warm-up failed")

    try:
        yield
    finally:
        shutdown_chat_workers()
        close_database_pools()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Backend API gateway for the Vietnamese personal income tax RAG chatbot.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()

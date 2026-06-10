from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Header, HTTPException, status

from backend.app.core.config import get_settings
from backend.app.schemas.rag import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
)
from backend.app.services.chat_service import ChatGatewayService


logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_chat_service() -> ChatGatewayService:
    return ChatGatewayService(get_settings())


@router.get(
    "/health",
    response_model=HealthResponse,
    response_model_exclude_none=True,
)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_version=settings.app_version,
        embedding_model=settings.embedding_model_name,
        database_configured=settings.database_configured,
        supabase_auth_configured=settings.supabase_auth_configured,
    )


@router.post(
    "/api/v1/search",
    response_model=SearchResponse,
    response_model_exclude_none=True,
)
def search(request: SearchRequest) -> SearchResponse:
    try:
        return get_chat_service().search(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.exception("Search service unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service is temporarily unavailable.",
        ) from exc


@router.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> ChatResponse:
    try:
        return get_chat_service().chat(
            request,
            authorization=authorization,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.exception("Chat service unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service is temporarily unavailable.",
        ) from exc
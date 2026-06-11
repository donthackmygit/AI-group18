from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Header, HTTPException, Query, status

from backend.app.core.config import get_settings
from backend.app.schemas.monitoring import (
    IngestionLogListResponse,
    MonitoringDashboardResponse,
    QueryLogListResponse,
)
from backend.app.schemas.rag import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
)
from backend.app.services.chat_service import ChatGatewayService
from backend.app.services.monitoring_service import MonitoringService


logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_chat_service() -> ChatGatewayService:
    return ChatGatewayService(get_settings())


@lru_cache(maxsize=1)
def get_monitoring_service() -> MonitoringService:
    return MonitoringService(get_settings())


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


@router.get(
    "/api/v1/monitoring/dashboard",
    response_model=MonitoringDashboardResponse,
    response_model_exclude_none=True,
)
def monitoring_dashboard(
    days: int = Query(default=7, ge=1, le=365),
) -> MonitoringDashboardResponse:
    try:
        return get_monitoring_service().dashboard(days=days)
    except RuntimeError as exc:
        logger.exception("Monitoring dashboard unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/v1/monitoring/query-logs",
    response_model=QueryLogListResponse,
    response_model_exclude_none=True,
)
def list_query_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    days: int | None = Query(default=None, ge=1, le=365),
) -> QueryLogListResponse:
    try:
        return get_monitoring_service().list_query_logs(
            limit=limit,
            offset=offset,
            status=status_filter,
            days=days,
        )
    except RuntimeError as exc:
        logger.exception("Query logs unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/v1/monitoring/ingestion-logs",
    response_model=IngestionLogListResponse,
    response_model_exclude_none=True,
)
def list_ingestion_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    document_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> IngestionLogListResponse:
    try:
        return get_monitoring_service().list_ingestion_logs(
            limit=limit,
            offset=offset,
            document_id=document_id,
            status=status_filter,
        )
    except RuntimeError as exc:
        logger.exception("Ingestion logs unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
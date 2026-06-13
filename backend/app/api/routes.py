from __future__ import annotations

import hmac
import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from backend.app.core.config import get_settings
from backend.app.schemas.document_management import (
    DocumentChunkListResponse,
    DocumentIngestionResponse,
    DocumentListResponse,
    DocumentMutationResponse,
    DocumentUpdateRequest,
    DocumentUploadRequest,
)
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
from backend.app.services.document_management_service import DocumentManagementService
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.supabase_auth_service import SupabaseAuthService


logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_chat_service() -> ChatGatewayService:
    return ChatGatewayService(get_settings())


@lru_cache(maxsize=1)
def get_monitoring_service() -> MonitoringService:
    return MonitoringService(get_settings())


@lru_cache(maxsize=1)
def get_document_management_service() -> DocumentManagementService:
    return DocumentManagementService(get_settings())


@lru_cache(maxsize=1)
def get_auth_service() -> SupabaseAuthService:
    return SupabaseAuthService(get_settings())


def require_monitoring_access(
    authorization: str | None = Header(default=None),
    x_monitoring_token: str | None = Header(default=None, alias="X-Monitoring-Token"),
) -> None:
    settings = get_settings()

    if _is_valid_monitoring_api_key(settings.monitoring_api_key, x_monitoring_token):
        return

    try:
        user = get_auth_service().authenticate_authorization_header(authorization)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.exception("Monitoring authentication unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring authentication is temporarily unavailable.",
        ) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Monitoring requires authentication.",
        )

    admin_user_ids = set(settings.monitoring_admin_user_ids)
    if admin_user_ids and user.id not in admin_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Monitoring access is not allowed for this user.",
        )

    if settings.app_env == "production" and not admin_user_ids and not settings.monitoring_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring admin access is not configured.",
        )


def _is_valid_monitoring_api_key(configured_key: str, provided_key: str | None) -> bool:
    return bool(
        configured_key
        and provided_key
        and hmac.compare_digest(configured_key, provided_key)
    )


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
    _: None = Depends(require_monitoring_access),
) -> MonitoringDashboardResponse:
    try:
        return get_monitoring_service().dashboard(days=days)
    except Exception as exc:
        logger.exception("Monitoring dashboard unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring dashboard is temporarily unavailable.",
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
    _: None = Depends(require_monitoring_access),
) -> QueryLogListResponse:
    try:
        return get_monitoring_service().list_query_logs(
            limit=limit,
            offset=offset,
            status=status_filter,
            days=days,
        )
    except Exception as exc:
        logger.exception("Query logs unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Query logs are temporarily unavailable.",
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
    _: None = Depends(require_monitoring_access),
) -> IngestionLogListResponse:
    try:
        return get_monitoring_service().list_ingestion_logs(
            limit=limit,
            offset=offset,
            document_id=document_id,
            status=status_filter,
        )
    except Exception as exc:
        logger.exception("Ingestion logs unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion logs are temporarily unavailable.",
        ) from exc


@router.get(
    "/api/v1/admin/documents",
    response_model=DocumentListResponse,
    response_model_exclude_none=True,
)
def list_admin_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_monitoring_access),
) -> DocumentListResponse:
    try:
        return get_document_management_service().list_documents(
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("Document list unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document management is temporarily unavailable.",
        ) from exc


@router.post(
    "/api/v1/admin/documents/upload",
    response_model=DocumentMutationResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def upload_admin_document(
    request: DocumentUploadRequest,
    _: None = Depends(require_monitoring_access),
) -> DocumentMutationResponse:
    try:
        return get_document_management_service().upload_document(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Document upload unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document upload is temporarily unavailable.",
        ) from exc


@router.get(
    "/api/v1/admin/documents/{document_id}",
    response_model=DocumentMutationResponse,
    response_model_exclude_none=True,
)
def get_admin_document(
    document_id: str,
    _: None = Depends(require_monitoring_access),
) -> DocumentMutationResponse:
    try:
        document = get_document_management_service().get_document(document_id)
        return DocumentMutationResponse(document=document)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except Exception as exc:
        logger.exception("Document detail unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document detail is temporarily unavailable.",
        ) from exc


@router.patch(
    "/api/v1/admin/documents/{document_id}",
    response_model=DocumentMutationResponse,
    response_model_exclude_none=True,
)
def update_admin_document(
    document_id: str,
    request: DocumentUpdateRequest,
    _: None = Depends(require_monitoring_access),
) -> DocumentMutationResponse:
    try:
        return get_document_management_service().update_document(
            document_id,
            request,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Document update unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document update is temporarily unavailable.",
        ) from exc


@router.post(
    "/api/v1/admin/documents/{document_id}/ingest",
    response_model=DocumentIngestionResponse,
    response_model_exclude_none=True,
)
def ingest_admin_document(
    document_id: str,
    _: None = Depends(require_monitoring_access),
) -> DocumentIngestionResponse:
    try:
        return get_document_management_service().ingest_document(document_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/v1/admin/documents/{document_id}/rerun-embedding",
    response_model=DocumentIngestionResponse,
    response_model_exclude_none=True,
)
def rerun_admin_document_embedding(
    document_id: str,
    _: None = Depends(require_monitoring_access),
) -> DocumentIngestionResponse:
    try:
        return get_document_management_service().ingest_document(
            document_id,
            rerun_embedding=True,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/v1/admin/documents/{document_id}/expire",
    response_model=DocumentMutationResponse,
    response_model_exclude_none=True,
)
def expire_admin_document(
    document_id: str,
    _: None = Depends(require_monitoring_access),
) -> DocumentMutationResponse:
    try:
        return get_document_management_service().mark_expired(document_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except Exception as exc:
        logger.exception("Document expire unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document status update is temporarily unavailable.",
        ) from exc


@router.delete(
    "/api/v1/admin/documents/{document_id}/search-index",
    response_model=DocumentMutationResponse,
    response_model_exclude_none=True,
)
def remove_admin_document_from_search(
    document_id: str,
    _: None = Depends(require_monitoring_access),
) -> DocumentMutationResponse:
    try:
        return get_document_management_service().remove_from_search(document_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except Exception as exc:
        logger.exception("Document search removal unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document search removal is temporarily unavailable.",
        ) from exc


@router.get(
    "/api/v1/admin/documents/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    response_model_exclude_none=True,
)
def list_admin_document_chunks(
    document_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_monitoring_access),
) -> DocumentChunkListResponse:
    try:
        return get_document_management_service().list_chunks(
            document_id=document_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("Document chunks unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document chunks are temporarily unavailable.",
        ) from exc

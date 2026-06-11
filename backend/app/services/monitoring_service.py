from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.repositories.monitoring_repository import MonitoringRepository
from backend.app.schemas.monitoring import (
    IngestionLogListResponse,
    MonitoringDashboardResponse,
    QueryLogListResponse,
)


class MonitoringService:
    def __init__(self, settings: Settings) -> None:
        self.repository = MonitoringRepository(settings)

    def dashboard(self, *, days: int = 7) -> MonitoringDashboardResponse:
        return self.repository.dashboard(days=days)

    def list_query_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        days: int | None = None,
    ) -> QueryLogListResponse:
        return self.repository.list_query_logs(
            limit=limit,
            offset=offset,
            status=status,
            days=days,
        )
    def list_ingestion_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        document_id: str | None = None,
        status: str | None = None,
    ) -> IngestionLogListResponse:
        return self.repository.list_ingestion_logs(
            limit=limit,
            offset=offset,
            document_id=document_id,
            status=status,
        )
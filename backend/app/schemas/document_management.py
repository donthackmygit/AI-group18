from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


DocumentLegalStatus = Literal[
    "draft",
    "effective",
    "partially_effective",
    "expired",
    "superseded",
]

DocumentIngestionStatus = Literal[
    "uploaded",
    "extracted",
    "ingesting",
    "indexed",
    "error",
    "removed_from_search",
]


class DocumentMetadataPayload(BaseModel):
    document_id: str | None = Field(
        default=None,
        max_length=120,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    document_title: str = Field(..., min_length=1, max_length=500)
    document_number: str | None = Field(default=None, max_length=120)
    document_type: str | None = Field(default=None, max_length=120)
    issuing_authority: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    status: DocumentLegalStatus = "draft"
    source_url: str | None = Field(default=None, max_length=1000)
    version: str | None = Field(default=None, max_length=80)
    topics: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "document_number",
        "document_type",
        "issuing_authority",
        "source_url",
        "version",
        "topics",
        "notes",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class DocumentUploadRequest(DocumentMetadataPayload):
    file_name: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


class DocumentUrlImportRequest(DocumentMetadataPayload):
    source_url: str = Field(..., min_length=1, max_length=1000)
    file_name: str | None = Field(default=None, max_length=255)


class DocumentUpdateRequest(BaseModel):
    document_title: str | None = Field(default=None, min_length=1, max_length=500)
    document_number: str | None = Field(default=None, max_length=120)
    document_type: str | None = Field(default=None, max_length=120)
    issuing_authority: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    status: DocumentLegalStatus | None = None
    source_url: str | None = Field(default=None, max_length=1000)
    version: str | None = Field(default=None, max_length=80)
    topics: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "document_number",
        "document_type",
        "issuing_authority",
        "source_url",
        "version",
        "topics",
        "notes",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class DocumentItem(BaseModel):
    document_id: str
    file_name: str | None = None
    document_title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    issue_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    status: str | None = None
    source_url: str | None = None
    local_path: str | None = None
    version: str | None = None
    topics: str | None = None
    notes: str | None = None
    extractor: str | None = None
    page_count: int | None = None
    extracted_char_count: int = 0
    ingestion_status: str = "uploaded"
    ingestion_error: str | None = None
    search_enabled: bool = False
    chunk_count: int = 0
    search_chunk_count: int = 0
    last_ingested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentDetail(DocumentItem):
    extracted_preview: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentListResponse(BaseModel):
    items: list[DocumentItem]
    limit: int
    offset: int


class DocumentMutationResponse(BaseModel):
    document: DocumentDetail


class DocumentIngestionResponse(BaseModel):
    document: DocumentDetail
    run_id: str | None = None
    chunk_count: int
    warning: str | None = None


class DocumentChunkItem(BaseModel):
    chunk_id: str
    document_id: str
    chunk_type: str | None = None
    content: str
    document_title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    article: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    chapter: str | None = None
    section: str | None = None
    status: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkItem]
    document_id: str
    limit: int
    offset: int

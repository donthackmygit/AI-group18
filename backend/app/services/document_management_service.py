from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.repositories.document_management_repository import (
    DocumentManagementRepository,
)
from backend.app.schemas.document_management import (
    DocumentChunkItem,
    DocumentChunkListResponse,
    DocumentDetail,
    DocumentIngestionResponse,
    DocumentItem,
    DocumentListResponse,
    DocumentMutationResponse,
    DocumentUpdateRequest,
    DocumentUploadRequest,
)
from backend.app.services.embedding_service import EmbeddingService


UPLOAD_ROOT = PROJECT_ROOT / "data" / "admin_uploads"
RAW_UPLOAD_DIR = UPLOAD_ROOT / "raw"
EXTRACTED_TEXT_DIR = UPLOAD_ROOT / "extracted"
CLEANED_TEXT_DIR = UPLOAD_ROOT / "cleaned"

MAX_UPLOAD_BYTES = 80 * 1024 * 1024
PREVIEW_MAX_CHARS = 6000
MAX_CHARS_PER_CHUNK = 1800

SUPPORTED_UPLOAD_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


@dataclass(frozen=True)
class ExtractedText:
    raw_text: str
    cleaned_text: str
    extractor: str
    page_count: int | None
    warning: str
    extracted_path: Path
    cleaned_path: Path


class DocumentManagementService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = DocumentManagementRepository(settings)
        self.embedding_service = EmbeddingService(settings)

    def list_documents(self, *, limit: int, offset: int) -> DocumentListResponse:
        rows = self.repository.list_documents(limit=limit, offset=offset)
        return DocumentListResponse(
            items=[DocumentItem(**_normalize_document_row(row)) for row in rows],
            limit=limit,
            offset=offset,
        )

    def get_document(self, document_id: str) -> DocumentDetail:
        row = self.repository.get_document(document_id)
        if row is None:
            raise KeyError(document_id)
        return DocumentDetail(**_normalize_document_row(row))

    def upload_document(self, request: DocumentUploadRequest) -> DocumentMutationResponse:
        document_id = _choose_document_id(
            explicit_id=request.document_id,
            document_number=request.document_number,
            file_name=request.file_name,
        )
        file_name = Path(request.file_name).name
        suffix = Path(file_name).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_UPLOAD_SUFFIXES))
            raise ValueError(f"Unsupported document format '{suffix}'. Supported: {supported}.")

        payload = _decode_base64(request.content_base64)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValueError("Uploaded document is too large.")

        _ensure_storage_dirs()
        raw_path = RAW_UPLOAD_DIR / f"{document_id}{suffix}"
        raw_path.write_bytes(payload)

        metadata = _metadata_from_payload(
            payload=request,
            document_id=document_id,
            file_name=file_name,
            local_path=_project_relative(raw_path),
        )
        extracted = _extract_and_clean(
            document_id=document_id,
            source_path=raw_path,
        )
        metadata.update(
            {
                "extractor": extracted.extractor,
                "page_count": extracted.page_count,
                "extracted_text_path": _project_relative(extracted.extracted_path),
                "cleaned_text_path": _project_relative(extracted.cleaned_path),
                "upload_warning": extracted.warning,
            }
        )

        document = self.repository.upsert_document(
            {
                "document_id": document_id,
                "file_name": file_name,
                "document_title": request.document_title,
                "document_number": request.document_number,
                "document_type": request.document_type,
                "issuing_authority": request.issuing_authority,
                "issue_date": request.issue_date,
                "effective_date": request.effective_date,
                "expiry_date": request.expiry_date,
                "status": request.status,
                "source_url": request.source_url,
                "local_path": _project_relative(raw_path),
                "version": request.version,
                "topics": request.topics,
                "notes": request.notes,
                "extractor": extracted.extractor,
                "page_count": extracted.page_count,
                "extracted_char_count": len(extracted.cleaned_text),
                "extracted_preview": _preview_text(extracted.cleaned_text),
                "ingestion_status": "extracted",
                "ingestion_error": None,
                "search_enabled": False,
                "chunk_count": 0,
                "metadata": metadata,
            }
        )

        self.repository.insert_ingestion_log(
            run_id=None,
            document_id=document_id,
            step="admin_upload_preview",
            status="success" if extracted.cleaned_text.strip() else "empty",
            input_path=_project_relative(raw_path),
            output_path=_project_relative(extracted.cleaned_path),
            char_count=len(extracted.cleaned_text),
            page_count=extracted.page_count,
            warning=extracted.warning or None,
            raw_log={"extractor": extracted.extractor},
        )

        return DocumentMutationResponse(
            document=DocumentDetail(**_normalize_document_row(document))
        )

    def update_document(
        self,
        document_id: str,
        request: DocumentUpdateRequest,
    ) -> DocumentMutationResponse:
        current = self.repository.get_document(document_id)
        if current is None:
            raise KeyError(document_id)
        current = self._ensure_managed_document(current)

        updates = request.model_dump(exclude_unset=True)
        if updates:
            metadata = dict(current.get("metadata") or {})
            metadata.update(_metadata_patch_from_updates(updates))
            updates["metadata"] = metadata

        document = self.repository.update_document(document_id, updates)
        return DocumentMutationResponse(
            document=DocumentDetail(**_normalize_document_row(document))
        )

    def ingest_document(
        self,
        document_id: str,
        *,
        rerun_embedding: bool = False,
    ) -> DocumentIngestionResponse:
        document = self.repository.get_document(document_id)
        if document is None:
            raise KeyError(document_id)
        document = self._ensure_managed_document(document)

        run_name = "admin_rerun_embedding" if rerun_embedding else "admin_ingestion"
        run_id = self.repository.create_ingestion_run(
            document_id=document_id,
            run_name=run_name,
        )
        self.repository.update_document(
            document_id,
            {
                "ingestion_status": "ingesting",
                "ingestion_error": None,
            },
        )

        try:
            cleaned_text = self._load_cleaned_text(document)
            metadata = _document_metadata_for_chunks(document)

            parsed = _parse_document_structure(
                document_id=document_id,
                text=cleaned_text,
                metadata=metadata,
            )
            chunks = _chunk_parsed_document(parsed)
            chunks = [_enrich_chunk(chunk, metadata) for chunk in chunks]
            if not chunks:
                raise ValueError("No chunks were created from this document.")

            embedding_inputs = [_embedding_input_for_chunk(chunk) for chunk in chunks]
            embeddings = self.embedding_service.encode_passages(embedding_inputs)
            self.repository.replace_chunks(
                document_id=document_id,
                chunks=chunks,
                embeddings=embeddings,
            )
            updated = self.repository.update_indexed_document_state(
                document_id=document_id,
                chunk_count=len(chunks),
                ingestion_status="indexed",
                ingestion_error=None,
            )
            self.repository.insert_ingestion_log(
                run_id=run_id,
                document_id=document_id,
                step=run_name,
                status="success",
                input_path=document.get("local_path"),
                output_path="rag.chunks",
                char_count=len(cleaned_text),
                chunk_count=len(chunks),
                page_count=document.get("page_count"),
                raw_log={
                    "parse_status": parsed.get("parse_status"),
                    "article_count": parsed.get("article_count"),
                    "paragraph_count": parsed.get("paragraph_count"),
                    "rerun_embedding": rerun_embedding,
                },
            )
            self.repository.finish_ingestion_run(
                run_id=run_id,
                status="success",
                success_count=1,
                warning_count=0,
                error_count=0,
            )
            return DocumentIngestionResponse(
                document=DocumentDetail(**_normalize_document_row(updated)),
                run_id=run_id,
                chunk_count=len(chunks),
            )
        except Exception as exc:
            error_message = str(exc)
            updated = self.repository.update_document(
                document_id,
                {
                    "ingestion_status": "error",
                    "ingestion_error": error_message,
                },
            )
            self.repository.insert_ingestion_log(
                run_id=run_id,
                document_id=document_id,
                step=run_name,
                status="error",
                input_path=document.get("local_path"),
                error_message=error_message,
                raw_log={"error_type": exc.__class__.__name__},
            )
            self.repository.finish_ingestion_run(
                run_id=run_id,
                status="error",
                success_count=0,
                warning_count=0,
                error_count=1,
                note=error_message,
            )
            raise RuntimeError(error_message) from exc

    def mark_expired(self, document_id: str) -> DocumentMutationResponse:
        current = self.repository.get_document(document_id)
        if current is None:
            raise KeyError(document_id)
        self._ensure_managed_document(current)
        document = self.repository.mark_expired(
            document_id=document_id,
            expiry_date=date.today(),
        )
        self.repository.insert_ingestion_log(
            run_id=None,
            document_id=document_id,
            step="admin_mark_expired",
            status="success",
            warning="Document and indexed chunks were marked expired.",
        )
        return DocumentMutationResponse(
            document=DocumentDetail(**_normalize_document_row(document))
        )

    def remove_from_search(self, document_id: str) -> DocumentMutationResponse:
        current = self.repository.get_document(document_id)
        if current is None:
            raise KeyError(document_id)
        self._ensure_managed_document(current)
        document = self.repository.remove_from_search(document_id)
        self.repository.insert_ingestion_log(
            run_id=None,
            document_id=document_id,
            step="admin_remove_from_search",
            status="success",
            warning="Indexed chunks were deleted from rag.chunks.",
        )
        return DocumentMutationResponse(
            document=DocumentDetail(**_normalize_document_row(document))
        )

    def list_chunks(
        self,
        *,
        document_id: str,
        limit: int,
        offset: int,
    ) -> DocumentChunkListResponse:
        rows = self.repository.list_chunks(
            document_id=document_id,
            limit=limit,
            offset=offset,
        )
        return DocumentChunkListResponse(
            items=[DocumentChunkItem(**row) for row in rows],
            document_id=document_id,
            limit=limit,
            offset=offset,
        )

    def _ensure_managed_document(self, document: dict[str, Any]) -> dict[str, Any]:
        metadata = document.get("metadata") or {}
        if metadata.get("source") != "rag.chunks":
            return document

        local_path = document.get("local_path")
        return self.repository.upsert_document(
            {
                "document_id": document["document_id"],
                "file_name": Path(str(local_path)).name if local_path else document["document_id"],
                "document_title": document.get("document_title") or document["document_id"],
                "document_number": document.get("document_number"),
                "document_type": document.get("document_type"),
                "issuing_authority": document.get("issuing_authority"),
                "issue_date": document.get("issue_date"),
                "effective_date": document.get("effective_date"),
                "expiry_date": document.get("expiry_date"),
                "status": _legal_status(document.get("status")),
                "source_url": document.get("source_url"),
                "local_path": local_path,
                "version": document.get("version"),
                "topics": document.get("topics"),
                "notes": document.get("notes"),
                "extractor": document.get("extractor"),
                "page_count": document.get("page_count"),
                "extracted_char_count": document.get("extracted_char_count") or 0,
                "extracted_preview": document.get("extracted_preview"),
                "ingestion_status": "indexed",
                "ingestion_error": None,
                "search_enabled": True,
                "chunk_count": document.get("search_chunk_count") or document.get("chunk_count") or 0,
                "metadata": {
                    "source": "rag.documents",
                    "created_from": "existing_rag_chunks",
                    "document_id": document["document_id"],
                    "title": document.get("document_title"),
                    "document_title": document.get("document_title"),
                    "document_name": document.get("document_title"),
                    "document_number": document.get("document_number"),
                    "document_type": document.get("document_type"),
                    "issuing_authority": document.get("issuing_authority"),
                    "issue_date": _date_or_none(document.get("issue_date")),
                    "effective_date": _date_or_none(document.get("effective_date")),
                    "expiry_date": _date_or_none(document.get("expiry_date")),
                    "status": _legal_status(document.get("status")),
                    "source_url": document.get("source_url"),
                    "local_path": local_path,
                },
            }
        )

    def _load_cleaned_text(self, document: dict[str, Any]) -> str:
        metadata = document.get("metadata") or {}
        cleaned_path = _resolve_project_path(metadata.get("cleaned_text_path"))
        if cleaned_path and cleaned_path.exists():
            return cleaned_path.read_text(encoding="utf-8", errors="ignore")

        source_path = _resolve_project_path(document.get("local_path"))
        if source_path is None or not source_path.exists():
            raise FileNotFoundError("Document source file is missing.")

        extracted = _extract_and_clean(
            document_id=document["document_id"],
            source_path=source_path,
        )
        metadata.update(
            {
                "extracted_text_path": _project_relative(extracted.extracted_path),
                "cleaned_text_path": _project_relative(extracted.cleaned_path),
                "extractor": extracted.extractor,
                "page_count": extracted.page_count,
            }
        )
        self.repository.update_document(
            document["document_id"],
            {
                "extractor": extracted.extractor,
                "page_count": extracted.page_count,
                "extracted_char_count": len(extracted.cleaned_text),
                "extracted_preview": _preview_text(extracted.cleaned_text),
                "metadata": metadata,
            },
        )
        return extracted.cleaned_text


def _ensure_storage_dirs() -> None:
    for path in (RAW_UPLOAD_DIR, EXTRACTED_TEXT_DIR, CLEANED_TEXT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _decode_base64(value: str) -> bytes:
    raw_value = value.split(",", 1)[1] if "," in value[:100] else value
    try:
        return base64.b64decode(raw_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64.") from exc


def _choose_document_id(
    *,
    explicit_id: str | None,
    document_number: str | None,
    file_name: str,
) -> str:
    source = explicit_id or document_number or Path(file_name).stem
    document_id = _safe_identifier(source).upper()
    if not document_id:
        document_id = f"DOC_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return document_id[:120]


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return re.sub(r"_+", "_", normalized).strip("_")


def _extract_and_clean(*, document_id: str, source_path: Path) -> ExtractedText:
    _ensure_storage_dirs()
    raw_text_path = EXTRACTED_TEXT_DIR / f"{document_id}.txt"
    cleaned_text_path = CLEANED_TEXT_DIR / f"{document_id}.txt"

    suffix = source_path.suffix.lower()
    if suffix in {".txt", ".html", ".htm"}:
        raw_text = source_path.read_text(encoding="utf-8", errors="ignore")
        extractor = "plain-text" if suffix == ".txt" else "local-html-text"
        page_count = None
        warning = ""
    else:
        from scripts.document_loader import LoaderOptions, load_document

        extracted = load_document(
            source_path,
            LoaderOptions(ocr_enabled=True),
        )
        raw_text = extracted.text
        extractor = extracted.extractor
        page_count = extracted.page_count
        warning = extracted.warning

    from scripts.text_cleaner import clean_text

    cleaned_text = clean_text(raw_text)
    raw_text_path.write_text(raw_text, encoding="utf-8")
    cleaned_text_path.write_text(cleaned_text, encoding="utf-8")

    return ExtractedText(
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        extractor=extractor,
        page_count=page_count,
        warning=warning,
        extracted_path=raw_text_path,
        cleaned_path=cleaned_text_path,
    )


def _metadata_from_payload(
    *,
    payload: DocumentUploadRequest,
    document_id: str,
    file_name: str,
    local_path: str,
) -> dict[str, Any]:
    metadata = payload.model_dump(mode="json", exclude={"content_base64"})
    metadata.update(
        {
            "document_id": document_id,
            "file_name": file_name,
            "title": payload.document_title,
            "document_title": payload.document_title,
            "document_name": payload.document_title,
            "source_type": "upload",
            "local_path": local_path,
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return metadata


def _metadata_patch_from_updates(updates: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key, value in updates.items():
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        metadata[key] = value
        if key == "document_title":
            metadata["title"] = value
            metadata["document_name"] = value
    return metadata


def _document_metadata_for_chunks(document: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(document.get("metadata") or {})
    title = document.get("document_title")
    metadata.update(
        {
            "document_id": document.get("document_id"),
            "file_name": document.get("file_name"),
            "title": title,
            "document_title": title,
            "document_name": title,
            "document_number": document.get("document_number"),
            "document_type": document.get("document_type"),
            "issuing_authority": document.get("issuing_authority"),
            "issue_date": _date_or_none(document.get("issue_date")),
            "effective_date": _date_or_none(document.get("effective_date")),
            "expiry_date": _date_or_none(document.get("expiry_date")),
            "status": document.get("status"),
            "source_type": "upload",
            "source_url": document.get("source_url"),
            "local_path": document.get("local_path"),
            "topics": document.get("topics"),
            "version": document.get("version"),
            "notes": document.get("notes"),
        }
    )
    return metadata


def _parse_document_structure(
    *,
    document_id: str,
    text: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    from scripts.document_structure_parser import parse_document_structure

    return parse_document_structure(
        document_id=document_id,
        text=text,
        metadata=metadata,
    )


def _chunk_parsed_document(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    from scripts.chunker import chunk_document, ensure_unique_chunk_ids

    chunks = chunk_document(parsed, max_chars=MAX_CHARS_PER_CHUNK)
    ensure_unique_chunk_ids(chunks)
    return chunks


def _enrich_chunk(chunk: dict[str, Any], document_metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        **document_metadata,
        **(chunk.get("metadata") or {}),
    }
    title = metadata.get("document_title") or metadata.get("title")
    metadata["document_title"] = title
    metadata["document_name"] = title
    return {
        **chunk,
        "document_id": document_metadata["document_id"],
        "metadata": metadata,
    }


def _embedding_input_for_chunk(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    parts = [
        metadata.get("document_type"),
        metadata.get("document_number"),
        metadata.get("document_title"),
        metadata.get("issuing_authority"),
        metadata.get("article"),
        metadata.get("article_title"),
        chunk.get("text"),
    ]
    return "\n".join(str(part) for part in parts if part)


def _preview_text(text: str) -> str:
    text = text.strip()
    if len(text) <= PREVIEW_MAX_CHARS:
        return text
    return text[:PREVIEW_MAX_CHARS].rsplit(" ", 1)[0].rstrip() + "..."


def _project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _resolve_project_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _date_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _legal_status(value: Any) -> str:
    status = str(value or "").strip()
    if status in {"draft", "effective", "partially_effective", "expired", "superseded"}:
        return status
    return "effective"


def _normalize_document_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["metadata"] = normalized.get("metadata") or {}
    normalized["chunk_count"] = normalized.get("chunk_count") or 0
    normalized["search_chunk_count"] = normalized.get("search_chunk_count") or 0
    normalized["extracted_char_count"] = normalized.get("extracted_char_count") or 0
    normalized["search_enabled"] = bool(normalized.get("search_enabled"))
    return normalized

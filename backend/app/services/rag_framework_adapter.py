from __future__ import annotations

from typing import Any

from backend.app.schemas.rag import Citation


def build_langchain_documents(citations: list[Citation]) -> tuple[str, list[Any]]:
    try:
        from langchain_core.documents import Document
    except ModuleNotFoundError:
        return "custom_pipeline_langchain_core_not_installed", []

    documents = []
    for citation in citations:
        metadata = {
            **(citation.metadata or {}),
            "citation_id": citation.citation_id,
            "chunk_id": citation.chunk_id,
            "document_id": citation.document_id,
            "document_number": citation.document_number,
            "article": citation.article,
            "source_url": citation.source_url,
        }
        documents.append(
            Document(
                page_content=citation.content,
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
        )

    return "langchain_core_documents", documents

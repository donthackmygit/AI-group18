from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

from backend.app.schemas.context import (
    ContextBuilderStrategy,
    ContextBuildResult,
    ContextSource,
)
from backend.app.schemas.rag import Citation
from backend.app.services.rag_framework_adapter import build_langchain_documents


MIN_TRUNCATED_BLOCK_TOKENS = 80
TRUNCATION_MARKER = "[Content truncated by context token limit.]"


@dataclass(frozen=True)
class ContextPayload:
    citations: list[Citation]
    result: ContextBuildResult


class ContextBuilderService:
    def build(self, citations: list[Citation], max_tokens: int) -> ContextPayload:
        if not citations:
            return ContextPayload(
                citations=[],
                result=ContextBuildResult(
                    strategy=ContextBuilderStrategy.SOURCE_BLOCKS,
                    applied=False,
                    max_tokens=max_tokens,
                    estimated_tokens=0,
                    input_count=0,
                    unique_count=0,
                    included_count=0,
                    duplicate_removed_count=0,
                    skipped_by_token_limit_count=0,
                    truncated_count=0,
                    context_text="",
                    note="No re-ranked citations available for context building.",
                ),
            )

        unique_citations = _deduplicate(citations)
        sorted_citations = sorted(unique_citations, key=_legal_sort_key)

        context_blocks: list[str] = []
        context_sources: list[ContextSource] = []
        included_citations: list[Citation] = []
        estimated_tokens = 0
        skipped_by_token_limit_count = 0
        truncated_count = 0

        for citation in sorted_citations:
            citation_id = f"SOURCE_{len(included_citations) + 1}"
            block = _format_context_block(citation, citation_id, citation.content)
            block_tokens = estimate_tokens(block)
            remaining_tokens = max_tokens - estimated_tokens

            if block_tokens <= remaining_tokens:
                truncated = False
                final_block = block
                final_tokens = block_tokens
            elif remaining_tokens >= MIN_TRUNCATED_BLOCK_TOKENS:
                truncated_content = _truncate_content_to_fit(
                    citation=citation,
                    citation_id=citation_id,
                    max_tokens=remaining_tokens,
                )
                final_block = _format_context_block(citation, citation_id, truncated_content)
                final_tokens = estimate_tokens(final_block)
                truncated = True
            else:
                skipped_by_token_limit_count += 1
                continue

            if final_tokens > remaining_tokens:
                skipped_by_token_limit_count += 1
                continue

            context_blocks.append(final_block)
            estimated_tokens += final_tokens
            if truncated:
                truncated_count += 1
            context_sources.append(
                _to_context_source(
                    citation=citation,
                    citation_id=citation_id,
                    estimated_tokens=final_tokens,
                    truncated=truncated,
                )
            )
            included_citations.append(citation.model_copy(update={"citation_id": citation_id}))

        skipped_by_token_limit_count = len(sorted_citations) - len(included_citations)

        rag_framework, framework_documents = build_langchain_documents(included_citations)
        return ContextPayload(
            citations=included_citations,
            result=ContextBuildResult(
                strategy=ContextBuilderStrategy.SOURCE_BLOCKS,
                applied=True,
                max_tokens=max_tokens,
                estimated_tokens=estimated_tokens,
                input_count=len(citations),
                unique_count=len(unique_citations),
                included_count=len(included_citations),
                duplicate_removed_count=len(citations) - len(unique_citations),
                skipped_by_token_limit_count=skipped_by_token_limit_count,
                truncated_count=truncated_count,
                context_text="\n\n".join(context_blocks),
                sources=context_sources,
                rag_framework=rag_framework,
                framework_document_count=len(framework_documents),
                note=(
                    "Context is assembled from re-ranked citations, de-duplicated by chunk/content, "
                    "ordered by legal metadata, exposed through an optional LangChain Document adapter, "
                    "and capped with an approximate token estimator."
                ),
            ),
        )


def estimate_tokens(text: str) -> int:
    compact = text.strip()
    if not compact:
        return 0
    word_count = len(re.findall(r"\S+", compact, flags=re.UNICODE))
    char_estimate = math.ceil(len(compact) / 4)
    word_estimate = math.ceil(word_count * 1.2)
    return max(1, char_estimate, word_estimate)


def _deduplicate(citations: list[Citation]) -> list[Citation]:
    seen_chunk_ids: set[str] = set()
    seen_content_keys: set[tuple[str, str]] = set()
    unique: list[Citation] = []

    for citation in citations:
        chunk_id = citation.chunk_id.strip()
        if chunk_id and chunk_id in seen_chunk_ids:
            continue

        content_hash = _content_hash(citation.content)
        content_key = (citation.document_id or citation.document_number or "", content_hash)
        if content_hash and content_key in seen_content_keys:
            continue

        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        if content_hash:
            seen_content_keys.add(content_key)
        unique.append(citation)

    return unique


def _content_hash(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content.strip().casefold())
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _legal_sort_key(citation: Citation) -> tuple[Any, ...]:
    metadata = citation.metadata or {}
    document_key = (
        citation.document_id
        or citation.document_number
        or metadata.get("document_id")
        or metadata.get("document_number")
        or citation.document_title
        or ""
    )
    return (
        citation.rerank_rank or citation.retrieval_rank or 9999,
        _status_rank(citation.status),
        _natural_key(str(document_key)),
        _natural_key(
            str(metadata.get("article_index") or citation.article_number or citation.article or "")
        ),
        _natural_key(str(metadata.get("clause_start") or metadata.get("clause") or "")),
        _natural_key(str(metadata.get("point_start") or metadata.get("point") or "")),
        _natural_key(str(metadata.get("sub_chunk_index") or "")),
    )


def _status_rank(status: str | None) -> int:
    if status and status.casefold() == "effective":
        return 0
    if status is None:
        return 1
    return 2


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    normalized = value.casefold().strip()
    if not normalized:
        return ((2, ""),)

    parts: list[tuple[int, int | str]] = []
    for part in re.split(r"(\d+)", normalized):
        if not part:
            continue
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part))
    return tuple(parts) or ((2, ""),)


def _format_context_block(citation: Citation, citation_id: str, content: str) -> str:
    metadata = citation.metadata or {}
    clause = _range_value(metadata.get("clause_start") or metadata.get("clause"), metadata.get("clause_end"))
    point = _range_value(metadata.get("point_start") or metadata.get("point"), metadata.get("point_end"))

    lines = [
        f"[{citation_id}]",
        f"Van ban: {_document_label(citation)}",
    ]
    _append_if_present(lines, "So hieu", citation.document_number)
    _append_if_present(lines, "Loai van ban", citation.document_type)
    _append_if_present(lines, "Dieu", _article_label(citation))
    _append_if_present(lines, "Khoan", clause)
    _append_if_present(lines, "Diem", point)
    _append_if_present(lines, "Trang thai", citation.status)
    _append_if_present(lines, "Hieu luc tu", _date_to_text(citation.effective_date))
    _append_if_present(lines, "Het hieu luc", _date_to_text(citation.expiry_date))
    _append_if_present(lines, "Nguon", citation.source_url or citation.local_path or citation.chunk_id)
    lines.extend(["Noi dung:", _normalize_content(content)])
    return "\n".join(lines).strip()


def _append_if_present(lines: list[str], label: str, value: str | None) -> None:
    if value:
        lines.append(f"{label}: {value}")


def _document_label(citation: Citation) -> str:
    return (
        citation.document_title
        or citation.document_number
        or citation.document_id
        or citation.chunk_id
        or "Unknown document"
    )


def _article_label(citation: Citation) -> str | None:
    if citation.article and citation.article_title and citation.article_title not in citation.article:
        return f"{citation.article} - {citation.article_title}"
    return citation.article or citation.article_title or citation.article_number


def _range_value(start: Any, end: Any) -> str | None:
    if start is None or start == "":
        return None
    if end is None or end == "" or str(end) == str(start):
        return str(start)
    return f"{start}-{end}"


def _range_label(label: str, start: Any, end: Any) -> str | None:
    value = _range_value(start, end)
    if value is None:
        return None
    return f"{label} {value}"


def _date_to_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_content(content: str) -> str:
    normalized_lines: list[str] = []
    previous_blank = False

    for raw_line in content.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue
        normalized_lines.append(line)
        previous_blank = False

    return "\n".join(normalized_lines).strip()


def _truncate_content_to_fit(citation: Citation, citation_id: str, max_tokens: int) -> str:
    normalized_content = _normalize_content(citation.content)
    marker_tokens = estimate_tokens(TRUNCATION_MARKER)
    max_content_tokens = max(max_tokens - marker_tokens, 0)
    char_budget = max(max_content_tokens * 4, 0)
    truncated = _trim_to_word_boundary(normalized_content[:char_budget])

    while truncated:
        candidate = f"{truncated}\n{TRUNCATION_MARKER}"
        block = _format_context_block(citation, citation_id, candidate)
        if estimate_tokens(block) <= max_tokens:
            return candidate
        truncated = _trim_to_word_boundary(truncated[: max(0, int(len(truncated) * 0.85))])

    return TRUNCATION_MARKER


def _trim_to_word_boundary(text: str) -> str:
    trimmed = text.rstrip()
    if " " not in trimmed:
        return trimmed
    return trimmed.rsplit(" ", 1)[0].rstrip()


def _to_context_source(
    citation: Citation,
    citation_id: str,
    estimated_tokens: int,
    truncated: bool,
) -> ContextSource:
    metadata = citation.metadata or {}
    return ContextSource(
        citation_id=citation_id,
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        document_title=citation.document_title,
        document_number=citation.document_number,
        document_type=citation.document_type,
        article=citation.article,
        article_number=citation.article_number,
        article_title=citation.article_title,
        clause=_range_label(
            "Khoan",
            metadata.get("clause_start") or metadata.get("clause"),
            metadata.get("clause_end"),
        ),
        point=_range_label(
            "Diem",
            metadata.get("point_start") or metadata.get("point"),
            metadata.get("point_end"),
        ),
        source_url=citation.source_url,
        local_path=citation.local_path,
        status=citation.status,
        effective_date=citation.effective_date,
        expiry_date=citation.expiry_date,
        similarity=citation.similarity,
        rerank_score=citation.rerank_score,
        retrieval_rank=citation.retrieval_rank,
        rerank_rank=citation.rerank_rank,
        estimated_tokens=estimated_tokens,
        truncated=truncated,
    )

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_DIR = PROJECT_ROOT / "data" / "processed" / "structured_documents"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
LOG_PATH = PROJECT_ROOT / "data" / "processed" / "chunker_log.csv"

APPROX_CHARS_PER_TOKEN = 4
MAX_TOKENS_PER_CHUNK = 900
OVERLAP_TOKENS = 80
MAX_CHARS_PER_CHUNK = MAX_TOKENS_PER_CHUNK * APPROX_CHARS_PER_TOKEN
MIN_CHARS_PER_CHUNK = 300
PARAGRAPH_OVERLAP = 1

DOCUMENT_METADATA_FIELDS = [
    "document_id",
    "file_name",
    "title",
    "document_number",
    "document_type",
    "issuing_authority",
    "issue_date",
    "effective_date",
    "expiry_date",
    "status",
    "source_type",
    "source_url",
    "local_path",
    "download_date",
    "topics",
    "version",
    "notes",
]

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?;:])\s+")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def normalize_text(text: Any) -> str:
    text = "" if text is None else str(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_id(value: Any, fallback: str = "NA") -> str:
    text = str(value or fallback).strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def prefixed_text(prefix_lines: list[str], body: str) -> str:
    parts = [normalize_text(line) for line in prefix_lines if normalize_text(line)]
    if body:
        parts.append(normalize_text(body))
    return normalize_text("\n".join(parts))


def hard_split(text: str, max_chars: int) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        cut = remaining.rfind(" ", 0, max_chars + 1)
        if cut < max_chars * 0.55:
            cut = max_chars
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    paragraph = normalize_text(paragraph)
    if len(paragraph) <= max_chars:
        return [paragraph] if paragraph else []

    sentences = [
        normalize_text(sentence)
        for sentence in SENTENCE_SPLIT_PATTERN.split(paragraph)
        if normalize_text(sentence)
    ]
    if len(sentences) <= 1:
        return hard_split(paragraph, max_chars)

    chunks: list[str] = []
    current: list[str] = []

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
            chunks.extend(hard_split(sentence, max_chars))
            continue

        candidate = " ".join(current + [sentence]).strip()
        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current).strip())
            current = [sentence]
        else:
            current.append(sentence)

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def split_plain_text(text: str, max_chars: int, overlap_tokens: int = OVERLAP_TOKENS) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = [paragraph for paragraph in text.split("\n") if paragraph.strip()]
    chunks: list[str] = []
    current: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            chunks.append("\n".join(current).strip())
            current = []

    for paragraph in paragraphs:
        paragraph = normalize_text(paragraph)
        if len(paragraph) > max_chars:
            flush_current()
            chunks.extend(split_long_paragraph(paragraph, max_chars))
            continue

        candidate = "\n".join(current + [paragraph]).strip()
        if current and len(candidate) > max_chars:
            flush_current()
            current.append(paragraph)
        else:
            current.append(paragraph)

    flush_current()
    return add_token_overlap(chunks, max_chars=max_chars, overlap_tokens=overlap_tokens)


def split_text_with_prefix(
    prefix_lines: list[str],
    body: str,
    max_chars: int,
) -> list[str]:
    prefix = prefixed_text(prefix_lines, "")
    body = normalize_text(body)
    if not body:
        return [prefix] if prefix else []

    if not prefix:
        return split_plain_text(body, max_chars)

    separator_len = 1
    body_budget = max_chars - len(prefix) - separator_len
    if body_budget < 200:
        return split_plain_text(prefixed_text(prefix_lines, body), max_chars)

    body_parts = split_plain_text(body, body_budget)
    return [prefixed_text(prefix_lines, body_part) for body_part in body_parts]


def add_token_overlap(parts: list[str], max_chars: int, overlap_tokens: int) -> list[str]:
    if overlap_tokens <= 0 or len(parts) <= 1:
        return parts

    overlapped = [parts[0]]
    for index, part in enumerate(parts[1:], start=1):
        tail = token_tail(parts[index - 1], overlap_tokens)
        while tail:
            candidate = normalize_text(f"{tail}\n{part}")
            if len(candidate) <= max_chars:
                overlapped.append(candidate)
                break
            words = tail.split()
            if len(words) <= 8:
                tail = ""
            else:
                tail = " ".join(words[len(words) // 2 :])
        else:
            overlapped.append(part)
    return overlapped


def token_tail(text: str, token_count: int) -> str:
    words = normalize_text(text).split()
    if len(words) <= token_count:
        return " ".join(words)
    return " ".join(words[-token_count:])


def article_heading(article: dict[str, Any]) -> str:
    label = normalize_text(article.get("article"))
    title = normalize_text(article.get("title"))
    if label and title:
        return f"{label}. {title}"
    return label or title


def article_context_lines(article: dict[str, Any], include_heading: bool = True) -> list[str]:
    lines = [
        normalize_text(article.get("chapter")),
        normalize_text(article.get("section")),
    ]
    if include_heading:
        lines.append(article_heading(article))
    return [line for line in lines if line]


def strip_article_heading(article: dict[str, Any], text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""

    label = normalize_text(article.get("article"))
    if not label:
        return text

    lines = text.split("\n")
    first_line = lines[0].strip() if lines else ""
    if first_line.lower().startswith(label.lower()):
        return normalize_text("\n".join(lines[1:]))
    return text


def extract_clause_intro(clause: dict[str, Any]) -> str:
    content = normalize_text(clause.get("content"))
    points = clause.get("points") or []
    if not content or not points:
        return content

    first_point = normalize_text(points[0].get("content"))
    if first_point:
        index = content.find(first_point)
        if index > 0:
            return normalize_text(content[:index])

    lines = content.split("\n")
    return lines[0].strip() if lines else ""


def document_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    source = doc.get("metadata") or {}
    metadata = {
        field: source.get(field, "")
        for field in DOCUMENT_METADATA_FIELDS
        if field in source or field == "document_id"
    }
    metadata["document_id"] = doc.get("document_id") or metadata.get("document_id", "")
    if metadata.get("title") and not metadata.get("document_name"):
        metadata["document_name"] = metadata["title"]
    return metadata


def enrich_metadata(
    doc: dict[str, Any],
    chunk_index: int,
    chunk_source_type: str,
    source_structure: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = document_metadata(doc)
    metadata.update(
        {
            "chunk_index": chunk_index,
            "chunk_source_type": chunk_source_type,
            "source_structure": source_structure,
            "parse_status": doc.get("parse_status", ""),
        }
    )
    if extra:
        metadata.update(extra)
    return metadata


def make_chunk(
    doc: dict[str, Any],
    chunk_id: str,
    chunk_type: str,
    text: str,
    chunk_index: int,
    chunk_source_type: str,
    source_structure: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    text = normalize_text(text)
    if not text:
        return None

    return {
        "chunk_id": chunk_id,
        "document_id": doc.get("document_id"),
        "chunk_type": chunk_type,
        "text": text,
        "char_count": len(text),
        "metadata": enrich_metadata(
            doc,
            chunk_index=chunk_index,
            chunk_source_type=chunk_source_type,
            source_structure=source_structure,
            extra=extra_metadata,
        ),
    }


def article_metadata(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "article": article.get("article"),
        "article_number": article.get("article_number"),
        "article_id": article_chunk_id(article),
        "article_index": article.get("_chunk_article_index"),
        "article_occurrence": article.get("_chunk_article_occurrence"),
        "article_title": article.get("title"),
        "chapter": article.get("chapter"),
        "section": article.get("section"),
    }


def article_chunk_id(article: dict[str, Any]) -> str:
    return safe_id(article.get("_chunk_article_id") or article.get("article_number"), "NA")


def add_article_chunk_ids(articles: list[dict[str, Any]]) -> None:
    article_numbers = [safe_id(article.get("article_number"), "NA") for article in articles]
    number_counts = Counter(article_numbers)
    number_occurrences: dict[str, int] = {}

    for article_index, article in enumerate(articles, start=1):
        article_number = safe_id(article.get("article_number"), "NA")
        number_occurrences[article_number] = number_occurrences.get(article_number, 0) + 1
        occurrence = number_occurrences[article_number]

        article["_chunk_article_index"] = article_index
        article["_chunk_article_occurrence"] = occurrence
        if number_counts[article_number] > 1:
            article["_chunk_article_id"] = f"{article_number}_OCC_{occurrence:03d}"
        else:
            article["_chunk_article_id"] = article_number


def append_chunk(chunks: list[dict[str, Any]], chunk: dict[str, Any] | None) -> None:
    if chunk:
        chunks.append(chunk)


def split_clause_by_points(
    doc: dict[str, Any],
    article: dict[str, Any],
    clause: dict[str, Any],
    article_number_id: str,
    max_chars: int,
    chunks: list[dict[str, Any]],
) -> None:
    prefix_lines = article_context_lines(article, include_heading=True)
    intro = extract_clause_intro(clause)
    points = clause.get("points") or []
    clause_label = clause.get("clause")
    clause_id = safe_id(clause_label, "NA")

    current_points: list[dict[str, Any]] = []
    current_texts: list[str] = []

    def flush_points() -> None:
        nonlocal current_points, current_texts
        if not current_texts:
            return

        point_start = current_points[0].get("point") if current_points else ""
        point_end = current_points[-1].get("point") if current_points else ""
        body = prefixed_text([intro], "\n".join(current_texts)) if intro else "\n".join(current_texts)
        text = prefixed_text(prefix_lines, body)
        sequence = len(
            [
                chunk
                for chunk in chunks
                if f"_ARTICLE_{article_number_id}_CLAUSE_{clause_id}_" in chunk["chunk_id"]
            ]
        ) + 1
        chunk_id = (
            f"{doc.get('document_id')}_ARTICLE_{article_number_id}_CLAUSE_{clause_id}"
            f"_POINT_{safe_id(point_start)}_TO_{safe_id(point_end)}_CHUNK_{sequence:03d}"
        )
        append_chunk(
            chunks,
            make_chunk(
                doc=doc,
                chunk_id=chunk_id,
                chunk_type="point_group",
                text=text,
                chunk_index=len(chunks) + 1,
                chunk_source_type="legal_document",
                source_structure="point_group",
                extra_metadata={
                    **article_metadata(article),
                    "clause_start": clause_label,
                    "clause_end": clause_label,
                    "point_start": point_start,
                    "point_end": point_end,
                    "split_reason": "clause_too_long",
                },
            ),
        )
        current_points = []
        current_texts = []

    for point in points:
        point_text = normalize_text(point.get("content"))
        if not point_text:
            continue

        body = prefixed_text([intro], point_text) if intro else point_text
        point_with_context = prefixed_text(prefix_lines, body)
        if len(point_with_context) > max_chars:
            flush_points()
            point_parts = split_text_with_prefix(prefix_lines + ([intro] if intro else []), point_text, max_chars)
            for part_index, part in enumerate(point_parts, start=1):
                chunk_id = (
                    f"{doc.get('document_id')}_ARTICLE_{article_number_id}_CLAUSE_{clause_id}"
                    f"_POINT_{safe_id(point.get('point'))}_CHUNK_{part_index:03d}"
                )
                append_chunk(
                    chunks,
                    make_chunk(
                        doc=doc,
                        chunk_id=chunk_id,
                        chunk_type="point_part",
                        text=part,
                        chunk_index=len(chunks) + 1,
                        chunk_source_type="legal_document",
                        source_structure="point",
                        extra_metadata={
                            **article_metadata(article),
                            "clause_start": clause_label,
                            "clause_end": clause_label,
                            "point_start": point.get("point"),
                            "point_end": point.get("point"),
                            "split_reason": "point_too_long",
                            "sub_chunk_index": part_index,
                            "sub_chunk_total": len(point_parts),
                        },
                    ),
                )
            continue

        candidate_texts = current_texts + [point_text]
        candidate_body = prefixed_text([intro], "\n".join(candidate_texts)) if intro else "\n".join(candidate_texts)
        candidate = prefixed_text(prefix_lines, candidate_body)
        if current_texts and len(candidate) > max_chars:
            flush_points()
        current_points.append(point)
        current_texts.append(point_text)

    flush_points()


def split_long_clause(
    doc: dict[str, Any],
    article: dict[str, Any],
    clause: dict[str, Any],
    article_number_id: str,
    max_chars: int,
    chunks: list[dict[str, Any]],
) -> None:
    if clause.get("points"):
        split_clause_by_points(doc, article, clause, article_number_id, max_chars, chunks)
        return

    clause_text = normalize_text(clause.get("content"))
    prefix_lines = article_context_lines(article, include_heading=True)
    clause_parts = split_text_with_prefix(prefix_lines, clause_text, max_chars)
    clause_label = clause.get("clause")
    clause_id = safe_id(clause_label, "NA")

    for part_index, part in enumerate(clause_parts, start=1):
        chunk_id = (
            f"{doc.get('document_id')}_ARTICLE_{article_number_id}_CLAUSE_{clause_id}"
            f"_CHUNK_{part_index:03d}"
        )
        append_chunk(
            chunks,
            make_chunk(
                doc=doc,
                chunk_id=chunk_id,
                chunk_type="clause_part",
                text=part,
                chunk_index=len(chunks) + 1,
                chunk_source_type="legal_document",
                source_structure="clause",
                extra_metadata={
                    **article_metadata(article),
                    "clause_start": clause_label,
                    "clause_end": clause_label,
                    "split_reason": "clause_too_long",
                    "sub_chunk_index": part_index,
                    "sub_chunk_total": len(clause_parts),
                },
            ),
        )


def chunk_article_by_clauses(
    doc: dict[str, Any],
    article: dict[str, Any],
    max_chars: int,
    chunks: list[dict[str, Any]],
) -> None:
    prefix_lines = article_context_lines(article, include_heading=True)
    article_number_id = article_chunk_id(article)
    clauses = article.get("clauses") or []
    current_clauses: list[dict[str, Any]] = []
    current_texts: list[str] = []

    def flush_clause_group() -> None:
        nonlocal current_clauses, current_texts
        if not current_texts:
            return

        clause_start = current_clauses[0].get("clause") if current_clauses else ""
        clause_end = current_clauses[-1].get("clause") if current_clauses else ""
        chunk_id = (
            f"{doc.get('document_id')}_ARTICLE_{article_number_id}"
            f"_CLAUSE_{safe_id(clause_start)}_TO_{safe_id(clause_end)}_CHUNK_001"
        )
        text = prefixed_text(prefix_lines, "\n".join(current_texts))
        append_chunk(
            chunks,
            make_chunk(
                doc=doc,
                chunk_id=chunk_id,
                chunk_type="clause_group",
                text=text,
                chunk_index=len(chunks) + 1,
                chunk_source_type="legal_document",
                source_structure="clause_group",
                extra_metadata={
                    **article_metadata(article),
                    "clause_start": clause_start,
                    "clause_end": clause_end,
                    "split_reason": "article_too_long",
                },
            ),
        )
        current_clauses = []
        current_texts = []

    for clause in clauses:
        clause_text = normalize_text(clause.get("content"))
        if not clause_text:
            continue

        clause_with_context = prefixed_text(prefix_lines, clause_text)
        if len(clause_with_context) > max_chars:
            flush_clause_group()
            split_long_clause(doc, article, clause, article_number_id, max_chars, chunks)
            continue

        candidate_texts = current_texts + [clause_text]
        candidate = prefixed_text(prefix_lines, "\n".join(candidate_texts))
        if current_texts and len(candidate) > max_chars:
            flush_clause_group()

        current_clauses.append(clause)
        current_texts.append(clause_text)

    flush_clause_group()


def chunk_article_by_text(
    doc: dict[str, Any],
    article: dict[str, Any],
    article_text: str,
    max_chars: int,
    chunks: list[dict[str, Any]],
) -> None:
    article_number_id = article_chunk_id(article)
    body = strip_article_heading(article, article_text)
    prefix_lines = article_context_lines(article, include_heading=True)
    parts = split_text_with_prefix(prefix_lines, body, max_chars)

    for part_index, part in enumerate(parts, start=1):
        chunk_id = f"{doc.get('document_id')}_ARTICLE_{article_number_id}_CHUNK_{part_index:03d}"
        append_chunk(
            chunks,
            make_chunk(
                doc=doc,
                chunk_id=chunk_id,
                chunk_type="article_part",
                text=part,
                chunk_index=len(chunks) + 1,
                chunk_source_type="legal_document",
                source_structure="article",
                extra_metadata={
                    **article_metadata(article),
                    "split_reason": "article_too_long",
                    "sub_chunk_index": part_index,
                    "sub_chunk_total": len(parts),
                },
            ),
        )


def chunk_article_document(
    doc: dict[str, Any],
    max_chars: int = MAX_CHARS_PER_CHUNK,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    articles = doc.get("articles") or []
    add_article_chunk_ids(articles)

    for article in articles:
        article_text = normalize_text(article.get("content"))
        if not article_text:
            continue

        article_number_id = article_chunk_id(article)
        full_article_text = prefixed_text(article_context_lines(article, include_heading=False), article_text)

        if len(full_article_text) <= max_chars:
            chunk_id = f"{doc.get('document_id')}_ARTICLE_{article_number_id}_CHUNK_001"
            append_chunk(
                chunks,
                make_chunk(
                    doc=doc,
                    chunk_id=chunk_id,
                    chunk_type="article",
                    text=full_article_text,
                    chunk_index=len(chunks) + 1,
                    chunk_source_type="legal_document",
                    source_structure="article",
                    extra_metadata=article_metadata(article),
                ),
            )
            continue

        if article.get("clauses"):
            chunk_article_by_clauses(doc, article, max_chars, chunks)
        else:
            chunk_article_by_text(doc, article, article_text, max_chars, chunks)

    return chunks


def paragraph_text(paragraph: Any) -> tuple[int | None, str]:
    if isinstance(paragraph, str):
        return None, normalize_text(paragraph)
    if isinstance(paragraph, dict):
        paragraph_id = paragraph.get("paragraph_id")
        try:
            paragraph_id = int(paragraph_id)
        except (TypeError, ValueError):
            paragraph_id = None
        return paragraph_id, normalize_text(paragraph.get("content") or paragraph.get("text"))
    return None, normalize_text(paragraph)


def chunk_paragraph_document(
    doc: dict[str, Any],
    max_chars: int = MAX_CHARS_PER_CHUNK,
) -> list[dict[str, Any]]:
    normalized_paragraphs = [
        (paragraph_id, text)
        for paragraph_id, text in (paragraph_text(paragraph) for paragraph in (doc.get("paragraphs") or []))
        if text
    ]

    chunks: list[dict[str, Any]] = []
    current: list[tuple[int | None, str]] = []

    def flush_current() -> None:
        nonlocal current
        if not current:
            return

        chunk_number = len(chunks) + 1
        text = "\n".join(paragraph for _, paragraph in current)
        first_id = current[0][0] if current[0][0] is not None else 1
        last_id = current[-1][0] if current[-1][0] is not None else first_id + len(current) - 1
        chunk_id = f"{doc.get('document_id')}_PARAGRAPH_CHUNK_{chunk_number:03d}"
        append_chunk(
            chunks,
            make_chunk(
                doc=doc,
                chunk_id=chunk_id,
                chunk_type="paragraph_group",
                text=text,
                chunk_index=chunk_number,
                chunk_source_type="dispatch",
                source_structure="paragraphs",
                extra_metadata={
                    "paragraph_start": first_id,
                    "paragraph_end": last_id,
                    "paragraph_count": len(current),
                    "overlap_paragraphs": PARAGRAPH_OVERLAP,
                },
            ),
        )
        current = []

    for paragraph_id, text in normalized_paragraphs:
        if len(text) > max_chars:
            flush_current()
            parts = split_plain_text(text, max_chars)
            for part_index, part in enumerate(parts, start=1):
                chunk_number = len(chunks) + 1
                paragraph_marker = paragraph_id if paragraph_id is not None else chunk_number
                chunk_id = (
                    f"{doc.get('document_id')}_PARAGRAPH_{safe_id(paragraph_marker)}"
                    f"_CHUNK_{part_index:03d}"
                )
                append_chunk(
                    chunks,
                    make_chunk(
                        doc=doc,
                        chunk_id=chunk_id,
                        chunk_type="paragraph_part",
                        text=part,
                        chunk_index=chunk_number,
                        chunk_source_type="dispatch",
                        source_structure="paragraphs",
                        extra_metadata={
                            "paragraph_start": paragraph_marker,
                            "paragraph_end": paragraph_marker,
                            "paragraph_count": 1,
                            "split_reason": "paragraph_too_long",
                            "sub_chunk_index": part_index,
                            "sub_chunk_total": len(parts),
                            "overlap_paragraphs": PARAGRAPH_OVERLAP,
                        },
                    ),
                )
            continue

        candidate = "\n".join([paragraph for _, paragraph in current] + [text]).strip()
        if current and len(candidate) > max_chars:
            flush_current()

        current.append((paragraph_id, text))

    flush_current()
    return chunks


def chunk_document(doc: dict[str, Any], max_chars: int = MAX_CHARS_PER_CHUNK) -> list[dict[str, Any]]:
    if doc.get("articles"):
        return chunk_article_document(doc, max_chars=max_chars)
    if doc.get("paragraphs"):
        return chunk_paragraph_document(doc, max_chars=max_chars)
    return []


def ensure_unique_chunk_ids(chunks: list[dict[str, Any]]) -> None:
    chunk_id_counts = Counter(chunk["chunk_id"] for chunk in chunks)
    duplicate_sequences: dict[str, int] = {}

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        if chunk_id_counts[chunk_id] <= 1:
            continue

        duplicate_sequences[chunk_id] = duplicate_sequences.get(chunk_id, 0) + 1
        sequence = duplicate_sequences[chunk_id]
        chunk["metadata"]["base_chunk_id"] = chunk_id
        chunk["metadata"]["duplicate_sequence"] = sequence
        chunk["metadata"]["duplicate_count"] = chunk_id_counts[chunk_id]
        chunk["chunk_id"] = f"{chunk_id}_SEQ_{sequence:03d}"


def chunk_stats(chunks: list[dict[str, Any]], max_chars: int) -> dict[str, Any]:
    char_counts = [chunk["char_count"] for chunk in chunks]
    if not char_counts:
        return {
            "min_chars": 0,
            "max_chars": 0,
            "avg_chars": 0,
            "total_chars": 0,
            "under_min_count": 0,
            "over_max_count": 0,
        }

    return {
        "min_chars": min(char_counts),
        "max_chars": max(char_counts),
        "avg_chars": round(mean(char_counts), 2),
        "total_chars": sum(char_counts),
        "under_min_count": sum(1 for count in char_counts if count < MIN_CHARS_PER_CHUNK),
        "over_max_count": sum(1 for count in char_counts if count > max_chars),
    }


def status_for_chunks(chunks: list[dict[str, Any]], stats: dict[str, Any]) -> tuple[str, str]:
    if not chunks:
        return "NO_CHUNK_CREATED", "No articles or paragraphs were available."
    if stats["over_max_count"]:
        return "OK_WITH_WARNINGS", f"{stats['over_max_count']} chunks exceed max_chars."
    return "OK", ""


def write_log(log_rows: list[dict[str, Any]]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id",
        "input_path",
        "output_path",
        "source_parse_status",
        "chunk_count",
        "min_chars",
        "max_chars",
        "avg_chars",
        "total_chars",
        "under_min_count",
        "over_max_count",
        "status",
        "note",
    ]
    with LOG_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)


def process_file(input_file: Path, max_chars: int) -> tuple[dict[str, Any], dict[str, Any]]:
    doc = json.loads(input_file.read_text(encoding="utf-8"))
    document_id = doc.get("document_id") or input_file.stem
    doc["document_id"] = document_id

    chunks = chunk_document(doc, max_chars=max_chars)
    ensure_unique_chunk_ids(chunks)
    stats = chunk_stats(chunks, max_chars=max_chars)
    status, note = status_for_chunks(chunks, stats)

    output_file = OUTPUT_DIR / f"{document_id}_chunks.json"
    output_data = {
        "document_id": document_id,
        "source_file": str(input_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "source_parse_status": doc.get("parse_status", ""),
        "chunked_at": datetime.now().isoformat(timespec="seconds"),
        "chunk_count": len(chunks),
        "max_tokens_per_chunk": MAX_TOKENS_PER_CHUNK,
        "overlap_tokens": OVERLAP_TOKENS,
        "max_chars_per_chunk": max_chars,
        "min_chars_per_chunk": MIN_CHARS_PER_CHUNK,
        "paragraph_overlap": PARAGRAPH_OVERLAP,
        "chunks": chunks,
    }
    output_file.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")

    log_row = {
        "document_id": document_id,
        "input_path": str(input_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "output_path": str(output_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "source_parse_status": doc.get("parse_status", ""),
        "chunk_count": len(chunks),
        **stats,
        "status": status,
        "note": note,
    }
    return output_data, log_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk structured tax documents for RAG ingestion.")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_CHARS_PER_CHUNK,
        help=f"Maximum characters per chunk. Default: {MAX_CHARS_PER_CHUNK}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    input_files = sorted(INPUT_DIR.glob("*.json"))
    log_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    total_chunks = 0

    for input_file in input_files:
        document_id = input_file.stem
        try:
            output_data, log_row = process_file(input_file, max_chars=args.max_chars)
            log_rows.append(log_row)
            total_chunks += output_data["chunk_count"]
            status_counts[log_row["status"]] = status_counts.get(log_row["status"], 0) + 1
            print(f"[{log_row['status']}] {output_data['document_id']}: {output_data['chunk_count']} chunks")
        except Exception as exc:
            status_counts["ERROR"] = status_counts.get("ERROR", 0) + 1
            log_rows.append(
                {
                    "document_id": document_id,
                    "input_path": str(input_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "output_path": "",
                    "source_parse_status": "",
                    "chunk_count": 0,
                    "min_chars": 0,
                    "max_chars": 0,
                    "avg_chars": 0,
                    "total_chars": 0,
                    "under_min_count": 0,
                    "over_max_count": 0,
                    "status": "ERROR",
                    "note": str(exc),
                }
            )
            print(f"[ERROR] {document_id}: {exc}")

    write_log(log_rows)

    print("\n===== CHUNKING SUMMARY =====")
    print(f"Documents: {len(input_files)}")
    print(f"Total chunks: {total_chunks}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}: {count}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Log: {LOG_PATH}")


if __name__ == "__main__":
    main()

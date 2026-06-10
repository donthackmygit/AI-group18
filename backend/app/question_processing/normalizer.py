from __future__ import annotations

import re
import unicodedata


WHITESPACE_RE = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFC", question or "")
    text = WHITESPACE_RE.sub(" ", text).strip().casefold()

    replacements = {
        "thuế tncn": "thuế TNCN",
        "tncn": "TNCN",
        "ng phụ thuộc": "người phụ thuộc",
        "npt": "người phụ thuộc",
        "bhxh": "bảo hiểm xã hội",
        "bhyt": "bảo hiểm y tế",
        "bhtn": "bảo hiểm thất nghiệp",
        "bn": "bao nhiêu",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*tr\b", r"\1 triệu", text)
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*triệu\b", r"\1 triệu", text)
    return WHITESPACE_RE.sub(" ", text).strip()

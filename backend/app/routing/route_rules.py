from __future__ import annotations

from backend.app.schemas.question_processing import ExtractedEntities


def get_missing_fields_for_tax_calculation(entities: ExtractedEntities) -> list[str]:
    missing: list[str] = []

    if entities.income is None:
        missing.append("gross_income")

    if entities.income_period is None:
        missing.append("income_period")

    if entities.insurance is None:
        missing.append("mandatory_insurance")

    if entities.dependents is None:
        missing.append("dependents")

    if entities.resident_status is None:
        missing.append("resident_status")

    return missing

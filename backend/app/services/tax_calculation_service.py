from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT
from backend.app.core.config import Settings
from backend.app.schemas.question_processing import ExtractedEntities
from backend.app.schemas.tax_calculation import (
    TaxBracketCalculation,
    TaxCalculationInput,
    TaxCalculationMethod,
    TaxCalculationResult,
    TaxCalculationStep,
    TaxPeriod,
)


RULES_PATH = PROJECT_ROOT / "data" / "tax_rules" / "personal_income_tax_salary_rules.json"
SHORT_TERM_CONTRACT_TYPES = {"short_term", "under_3_months", "no_contract", "seasonal"}


class TaxCalculationService:
    def __init__(self, settings: Settings | None = None, rules_path: Path = RULES_PATH) -> None:
        self.settings = settings
        self.rules_path = rules_path
        self._rules: list[dict[str, Any]] | None = None

    def calculate_salary_tax(
        self,
        entities: ExtractedEntities,
        effective_date: date | None = None,
        gross_income: int | None = None,
        income_period: str | None = None,
        mandatory_insurance: int | None = None,
        tax_exempt_income: int | None = None,
        dependents: int | None = None,
        charity_contributions: int | None = None,
        other_deductions: int | None = None,
        resident_status: str | None = None,
        tax_year: int | None = None,
        contract_type: str | None = None,
    ) -> TaxCalculationResult:
        missing_fields = _missing_fields(entities, gross_income, income_period)
        if missing_fields:
            return TaxCalculationResult(
                applied=False,
                missing_fields=missing_fields,
                warnings=["Missing required input for tax calculation."],
                note="Tax Calculation Service requires income and income_period.",
            )

        resolved_tax_year = tax_year or entities.tax_year or _year_from_effective_date(effective_date)
        rule = self._select_rule(resolved_tax_year)
        resolved_period = _resolve_period(income_period or entities.income_period)
        resolved_resident_status = (resident_status or entities.resident_status or "resident").strip().lower()
        assumption_warnings = _assumption_warnings(
            entities=entities,
            resident_status=resident_status,
            mandatory_insurance=mandatory_insurance,
            dependents=dependents,
        )
        resolved_input = TaxCalculationInput(
            gross_income=max(0, gross_income if gross_income is not None else entities.income or 0),
            income_period=resolved_period,
            tax_exempt_income=max(0, tax_exempt_income or 0),
            mandatory_insurance=max(
                0,
                mandatory_insurance if mandatory_insurance is not None else entities.insurance or 0,
            ),
            dependents=max(0, dependents if dependents is not None else entities.dependents or 0),
            charity_contributions=max(0, charity_contributions or 0),
            other_deductions=max(0, other_deductions or 0),
            resident_status=resolved_resident_status,
            tax_year=resolved_tax_year,
            contract_type=contract_type,
            effective_date=effective_date,
        )

        if resolved_resident_status == "non_resident":
            return self._calculate_non_resident(resolved_input, rule, assumption_warnings)

        if contract_type and contract_type.strip().lower() in SHORT_TERM_CONTRACT_TYPES:
            return self._calculate_short_term_withholding(
                resolved_input,
                rule,
                assumption_warnings,
            )

        return self._calculate_resident_progressive(
            resolved_input,
            rule,
            assumption_warnings,
        )

    def _calculate_resident_progressive(
        self,
        calculation_input: TaxCalculationInput,
        rule: dict[str, Any],
        assumption_warnings: list[str],
    ) -> TaxCalculationResult:
        multiplier = 12 if calculation_input.income_period == TaxPeriod.YEARLY else 1
        personal_deduction = int(rule["personal_deduction_monthly"]) * multiplier
        dependent_deduction = int(rule["dependent_deduction_monthly"]) * calculation_input.dependents * multiplier
        total_deductions = (
            calculation_input.tax_exempt_income
            + calculation_input.mandatory_insurance
            + personal_deduction
            + dependent_deduction
            + calculation_input.charity_contributions
            + calculation_input.other_deductions
        )
        taxable_income = max(0, calculation_input.gross_income - total_deductions)
        bracket_breakdown = _calculate_progressive_tax(
            taxable_income=taxable_income,
            brackets=_scale_brackets(rule["resident_brackets_monthly"], multiplier),
        )
        tax_amount = sum(bracket.tax_amount for bracket in bracket_breakdown)

        steps = [
            TaxCalculationStep(
                label="Gross taxable salary/wage income",
                amount=calculation_input.gross_income,
            ),
            TaxCalculationStep(
                label="Taxable income after deductions",
                amount=taxable_income,
                formula=(
                    "gross_income - tax_exempt_income - mandatory_insurance - personal_deduction "
                    "- dependent_deduction - charity_contributions - other_deductions"
                ),
            ),
            TaxCalculationStep(
                label="Personal income tax by progressive brackets",
                amount=tax_amount,
            ),
        ]
        warnings = _base_warnings(calculation_input, assumption_warnings)
        return _result(
            method=TaxCalculationMethod.RESIDENT_PROGRESSIVE,
            rule=rule,
            calculation_input=calculation_input,
            personal_deduction=personal_deduction,
            dependent_deduction=dependent_deduction,
            total_deductions=total_deductions,
            taxable_income=taxable_income,
            tax_amount=tax_amount,
            steps=steps,
            bracket_breakdown=bracket_breakdown,
            warnings=warnings,
        )

    def _calculate_non_resident(
        self,
        calculation_input: TaxCalculationInput,
        rule: dict[str, Any],
        assumption_warnings: list[str],
    ) -> TaxCalculationResult:
        taxable_income = max(0, calculation_input.gross_income - calculation_input.tax_exempt_income)
        rate = float(rule["non_resident_salary_rate"])
        tax_amount = round_vnd(taxable_income * rate)
        steps = [
            TaxCalculationStep(
                label="Non-resident salary/wage taxable income",
                amount=taxable_income,
                formula="gross_income - tax_exempt_income",
            ),
            TaxCalculationStep(
                label="Flat-rate tax for non-resident salary/wage income",
                amount=tax_amount,
                formula=f"taxable_income x {rate:.0%}",
            ),
        ]
        warnings = _base_warnings(calculation_input, assumption_warnings)
        warnings.append("Non-resident salary/wage income does not apply family deductions in this MVP.")
        return _result(
            method=TaxCalculationMethod.NON_RESIDENT_FLAT_RATE,
            rule=rule,
            calculation_input=calculation_input,
            personal_deduction=0,
            dependent_deduction=0,
            total_deductions=calculation_input.tax_exempt_income,
            taxable_income=taxable_income,
            tax_amount=tax_amount,
            steps=steps,
            bracket_breakdown=[],
            warnings=warnings,
        )

    def _calculate_short_term_withholding(
        self,
        calculation_input: TaxCalculationInput,
        rule: dict[str, Any],
        assumption_warnings: list[str],
    ) -> TaxCalculationResult:
        taxable_income = max(0, calculation_input.gross_income - calculation_input.tax_exempt_income)
        rate = float(rule["short_term_withholding_rate"])
        tax_amount = round_vnd(taxable_income * rate)
        steps = [
            TaxCalculationStep(
                label="Short-term/no-contract taxable payment",
                amount=taxable_income,
                formula="gross_income - tax_exempt_income",
            ),
            TaxCalculationStep(
                label="Withholding tax for short-term/no-contract resident income",
                amount=tax_amount,
                formula=f"taxable_income x {rate:.0%}",
            ),
        ]
        warnings = _base_warnings(calculation_input, assumption_warnings)
        warnings.append(
            "Short-term/no-contract withholding is a withholding estimate; annual finalization may differ."
        )
        return _result(
            method=TaxCalculationMethod.RESIDENT_SHORT_TERM_WITHHOLDING,
            rule=rule,
            calculation_input=calculation_input,
            personal_deduction=0,
            dependent_deduction=0,
            total_deductions=calculation_input.tax_exempt_income,
            taxable_income=taxable_income,
            tax_amount=tax_amount,
            steps=steps,
            bracket_breakdown=[],
            warnings=warnings,
        )

    def _select_rule(self, tax_year: int) -> dict[str, Any]:
        candidates = []
        for rule in self._load_rules():
            year_from = int(rule["tax_year_from"])
            year_to = rule.get("tax_year_to")
            if tax_year >= year_from and (year_to is None or tax_year <= int(year_to)):
                candidates.append(rule)

        if not candidates:
            raise RuntimeError(f"No personal income tax salary rule configured for tax year {tax_year}.")

        return sorted(candidates, key=lambda item: int(item["tax_year_from"]), reverse=True)[0]

    def _load_rules(self) -> list[dict[str, Any]]:
        if self._rules is None:
            db_rules = self._load_rules_from_database()
            if db_rules:
                self._rules = db_rules
                return self._rules

            try:
                payload = json.loads(self.rules_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise RuntimeError(f"Tax rule file not found: {self.rules_path}") from exc
            self._rules = list(payload.get("rules") or [])
        return self._rules

    def _load_rules_from_database(self) -> list[dict[str, Any]]:
        if self.settings is None or not self.settings.database_configured:
            return []

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError:
            return []

        sql = """
            select rule_payload
            from rag.tax_rules
            where is_active = true
            order by tax_year_from desc, rule_id;
        """

        try:
            with psycopg.connect(**self.settings.database_kwargs()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
        except Exception:
            return []

        rules = []
        for row in rows:
            payload = row.get("rule_payload")
            if isinstance(payload, dict):
                rules.append(payload)
        return rules


def _missing_fields(
    entities: ExtractedEntities,
    gross_income: int | None,
    income_period: str | None,
) -> list[str]:
    missing = []
    if gross_income is None and entities.income is None:
        missing.append("gross_income")
    if income_period is None and entities.income_period is None:
        missing.append("income_period")
    return missing


def _year_from_effective_date(effective_date: date | None) -> int:
    return (effective_date or date.today()).year


def _resolve_period(value: str | None) -> TaxPeriod:
    normalized = (value or "").strip().lower()
    if normalized in {"year", "yearly", "annual", "annually"}:
        return TaxPeriod.YEARLY
    return TaxPeriod.MONTHLY


def _scale_brackets(brackets: list[dict[str, Any]], multiplier: int) -> list[dict[str, Any]]:
    return [
        {
            "up_to": None if bracket.get("up_to") is None else int(bracket["up_to"]) * multiplier,
            "rate": float(bracket["rate"]),
        }
        for bracket in brackets
    ]


def _calculate_progressive_tax(
    taxable_income: int,
    brackets: list[dict[str, Any]],
) -> list[TaxBracketCalculation]:
    breakdown: list[TaxBracketCalculation] = []
    lower_bound = 0

    for bracket in brackets:
        upper_bound = bracket.get("up_to")
        rate = float(bracket["rate"])
        if upper_bound is None:
            taxable_amount = max(0, taxable_income - lower_bound)
        else:
            taxable_amount = max(0, min(taxable_income, int(upper_bound)) - lower_bound)

        if taxable_amount > 0:
            breakdown.append(
                TaxBracketCalculation(
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    taxable_amount=taxable_amount,
                    rate=rate,
                    tax_amount=round_vnd(taxable_amount * rate),
                )
            )

        if upper_bound is None or taxable_income <= int(upper_bound):
            break
        lower_bound = int(upper_bound)

    return breakdown


def round_vnd(value: float) -> int:
    return int(round(value))


def _assumption_warnings(
    *,
    entities: ExtractedEntities,
    resident_status: str | None,
    mandatory_insurance: int | None,
    dependents: int | None,
) -> list[str]:
    warnings: list[str] = []
    if resident_status is None and entities.resident_status is None:
        warnings.append(
            "Chưa cung cấp tình trạng cư trú; hệ thống tạm tính theo cá nhân cư trú."
        )
    if mandatory_insurance is None and entities.insurance is None:
        warnings.append(
            "Chưa cung cấp bảo hiểm bắt buộc; hệ thống tạm tính bảo hiểm bắt buộc bằng 0."
        )
    if dependents is None and entities.dependents is None:
        warnings.append(
            "Chưa cung cấp người phụ thuộc; hệ thống tạm tính số người phụ thuộc bằng 0."
        )
    return warnings


def _base_warnings(
    calculation_input: TaxCalculationInput,
    assumption_warnings: list[str],
) -> list[str]:
    warnings: list[str] = []
    if calculation_input.contract_type is None:
        warnings.append("contract_type was not provided; progressive resident method is used by default.")
    warnings.extend(assumption_warnings)
    return list(dict.fromkeys(warnings))


def _result(
    method: TaxCalculationMethod,
    rule: dict[str, Any],
    calculation_input: TaxCalculationInput,
    personal_deduction: int,
    dependent_deduction: int,
    total_deductions: int,
    taxable_income: int,
    tax_amount: int,
    steps: list[TaxCalculationStep],
    bracket_breakdown: list[TaxBracketCalculation],
    warnings: list[str],
) -> TaxCalculationResult:
    return TaxCalculationResult(
        applied=True,
        method=method,
        rule_id=rule["rule_id"],
        source_documents=list(rule.get("source_documents") or []),
        input=calculation_input,
        gross_income=calculation_input.gross_income,
        tax_exempt_income=calculation_input.tax_exempt_income,
        mandatory_insurance=calculation_input.mandatory_insurance,
        personal_deduction=personal_deduction,
        dependent_deduction=dependent_deduction,
        charity_contributions=calculation_input.charity_contributions,
        other_deductions=calculation_input.other_deductions,
        total_deductions=total_deductions,
        taxable_income=taxable_income,
        tax_amount=tax_amount,
        calculation_steps=steps,
        bracket_breakdown=bracket_breakdown,
        warnings=warnings,
        note="Tax Calculation Service computes salary/wage PIT; LLM should only explain this result.",
    )

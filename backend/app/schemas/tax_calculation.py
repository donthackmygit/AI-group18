from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class TaxCalculationMethod(str, Enum):
    RESIDENT_PROGRESSIVE = "RESIDENT_PROGRESSIVE"
    NON_RESIDENT_FLAT_RATE = "NON_RESIDENT_FLAT_RATE"
    RESIDENT_SHORT_TERM_WITHHOLDING = "RESIDENT_SHORT_TERM_WITHHOLDING"


class TaxPeriod(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class TaxCalculationInput(BaseModel):
    gross_income: int
    income_period: TaxPeriod
    tax_exempt_income: int = 0
    mandatory_insurance: int = 0
    dependents: int = 0
    charity_contributions: int = 0
    other_deductions: int = 0
    resident_status: str = "resident"
    tax_year: int
    contract_type: str | None = None
    effective_date: date | None = None


class TaxBracketCalculation(BaseModel):
    lower_bound: int
    upper_bound: int | None = None
    taxable_amount: int
    rate: float
    tax_amount: int


class TaxCalculationStep(BaseModel):
    label: str
    amount: int | None = None
    formula: str | None = None


class TaxCalculationResult(BaseModel):
    applied: bool
    method: TaxCalculationMethod | None = None
    rule_id: str | None = None
    source_documents: list[str] = Field(default_factory=list)
    input: TaxCalculationInput | None = None
    gross_income: int | None = None
    tax_exempt_income: int = 0
    mandatory_insurance: int = 0
    personal_deduction: int = 0
    dependent_deduction: int = 0
    charity_contributions: int = 0
    other_deductions: int = 0
    total_deductions: int = 0
    taxable_income: int | None = None
    tax_amount: int | None = None
    calculation_steps: list[TaxCalculationStep] = Field(default_factory=list)
    bracket_breakdown: list[TaxBracketCalculation] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    note: str | None = None

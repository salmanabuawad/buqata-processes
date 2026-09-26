"""RFQProcess — request for quotation (הצעת מחיר).

Automatic, non-editable distribution to every matching supplier; sealed
submissions; a simple opening (after the deadline, by an authorized procurement
participant); a comparison table; a human decision; a protocol.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from pydantic import Field, field_validator

from app.config import get_settings
from app.processes.base import DocumentRequirement, ProcessDefinition, StrictModel


class RFQDetails(StrictModel):
    quantity: int = Field(ge=1, le=1_000_000)
    unit: str = Field(default="יח'", max_length=40)
    technical_specification: str = Field(default="", max_length=20_000)
    expected_delivery_date: Optional[date] = None
    additional_requirements: str = Field(default="", max_length=10_000)
    service_regions: List[str] = Field(default_factory=list, max_length=20)


class RFQSubmission(StrictModel):
    price_before_vat_agorot: int = Field(gt=0, le=10_000_000_000)
    delivery_days: int = Field(ge=0, le=3650)
    warranty_months: int = Field(ge=0, le=240)
    payment_terms: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=5000)

    @field_validator("payment_terms", "notes")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class RFQProcess(ProcessDefinition):
    key = "rfq"
    names = {"he": "בקשה להצעת מחיר", "ar": "طلب عرض أسعار", "en": "Request for quotation"}
    reference_prefix = "RFQ"
    create_permission = "process.create.rfq"
    submitter_kind = "supplier"
    distribution = "category_match"
    sealed = True
    details_model = RFQDetails
    submission_model = RFQSubmission
    document_requirements = [
        DocumentRequirement("proposal", True, (".pdf",), names={"he": "הצעת מחיר (PDF)", "ar": "عرض السعر (PDF)", "en": "Proposal (PDF)"}),
        DocumentRequirement("technical_spec", False, (".pdf", ".docx", ".xlsx", ".doc", ".xls"),
                            names={"he": "מפרט טכני", "ar": "مواصفات فنية", "en": "Technical specification"}),
        DocumentRequirement("supporting", False, (".pdf", ".docx", ".xlsx", ".zip", ".png", ".jpg", ".jpeg"), multiple=True,
                            names={"he": "מסמכים נוספים", "ar": "مستندات إضافية", "en": "Supporting documents"}),
    ]
    default_opening_rules = [
        {"type": "time"},
        {"type": "role", "params": {"permission": "opening.initiate"}},
        {"type": "identity", "params": {"require_mfa": False}},
        {"type": "multi_approval"},
    ]
    default_required_approvals = 1
    timeline = ["draft", "published", "notified", "submission", "deadline", "opening", "evaluation", "decision", "closed"]
    protocol_types = ["rfq_opening", "rfq_decision"]

    def publish_problems(self, process, category_count: int) -> List[str]:
        problems = []
        if category_count == 0:
            problems.append("category_required")
        return problems

    def normalise_submission(self, payload: dict) -> dict:
        data = RFQSubmission.model_validate(payload).model_dump(mode="json")
        rate = Decimal(str(get_settings().vat_rate_percent))
        net = Decimal(data["price_before_vat_agorot"])
        vat = int((net * rate / Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        data["vat_rate_percent"] = float(rate)
        data["vat_agorot"] = vat
        data["total_agorot"] = int(net) + vat
        return data

    def comparison_row(self, payload: dict) -> dict:
        keys = ("price_before_vat_agorot", "vat_agorot", "total_agorot", "vat_rate_percent",
                "delivery_days", "warranty_months", "payment_terms", "notes")
        return {k: payload.get(k) for k in keys}

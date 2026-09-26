"""RFQProcess — request for quotation (הצעת מחיר).

Municipal policy for quotation requests is more flexible than for tenders:
* distribution is generated automatically from categories, and procurement may
  then add or remove suppliers — every change needs a reason and is recorded;
* the opening mode is chosen when the request is created (`opening_mode`):
  - `visible`: offers are shown to the process team as they arrive (default);
  - `sealed_anytime`: sealed; may be opened before the deadline, which closes
    submissions;
  - `sealed_after_deadline`: sealed; opens only after the deadline;
* a comparison table, a human decision and a protocol, as always.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Literal, Optional

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
    opening_mode: Literal["visible", "sealed_anytime", "sealed_after_deadline"] = "visible"


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
    distribution_editable = True
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
    # Base rules; `opening_rules_for` adds the time rule for sealed_after_deadline.
    default_opening_rules = [
        {"type": "role", "params": {"permission": "opening.initiate"}},
        {"type": "identity", "params": {"require_mfa": False}},
        {"type": "multi_approval"},
    ]
    default_required_approvals = 1
    timeline = ["draft", "published", "notified", "submission", "deadline", "opening", "evaluation", "decision", "closed"]
    protocol_types = ["rfq_opening", "rfq_decision"]

    def content_sealed(self, process) -> bool:
        return (process.details or {}).get("opening_mode", "visible") != "visible"

    def opening_rules_for(self, details: dict) -> List[dict]:
        rules = list(self.default_opening_rules)
        if details.get("opening_mode") == "sealed_after_deadline":
            rules.insert(0, {"type": "time"})
        return rules

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

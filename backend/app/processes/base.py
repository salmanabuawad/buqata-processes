"""ProcessDefinition — what makes a process type different, declared in one place.

Shared services ask the definition; they never branch on the type key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class DocumentRequirement:
    kind: str
    required: bool
    extensions: Tuple[str, ...]
    multiple: bool = False
    names: Dict[str, str] = field(default_factory=dict)


class ProcessDefinition:
    key: ClassVar[str]
    names: ClassVar[Dict[str, str]]
    reference_prefix: ClassVar[str]
    create_permission: ClassVar[str]
    submitter_kind: ClassVar[str]              # supplier | applicant
    distribution: ClassVar[str]                # category_match | public
    # Staff may add/remove recipients (with a recorded reason). Municipal
    # policy: allowed for quotation requests, never for formal tenders.
    distribution_editable: ClassVar[bool] = False
    # Submissions are always encrypted at rest (the vault). `sealed` says the
    # type supports sealing content until an opening; `content_sealed()` says
    # whether this particular process uses it.
    sealed: ClassVar[bool]
    details_model: ClassVar[Type[StrictModel]]
    submission_model: ClassVar[Optional[Type[StrictModel]]] = None
    document_requirements: ClassVar[List[DocumentRequirement]] = []
    default_opening_rules: ClassVar[List[dict]] = []
    default_required_approvals: ClassVar[int] = 1
    timeline: ClassVar[List[str]] = []
    protocol_types: ClassVar[List[str]] = []

    # ---- hooks -------------------------------------------------------------
    def content_sealed(self, process) -> bool:
        """True when offer content stays unreadable until the vault is opened."""
        return self.sealed

    def opening_rules_for(self, details: dict) -> List[dict]:
        """The opening policy a new process starts with (tunable until publication)."""
        return list(self.default_opening_rules)

    def timeline_for(self, process) -> List[str]:
        if self.content_sealed(process):
            return list(self.timeline)
        return [stage for stage in self.timeline if stage != "opening"]

    def validate_details(self, details: dict) -> dict:
        return self.details_model.model_validate(details).model_dump(mode="json")

    def publish_problems(self, process, category_count: int) -> List[str]:
        return []

    def normalise_submission(self, payload: dict) -> dict:
        """Validate a submission payload and add server-derived values."""
        if self.submission_model is None:
            raise NotImplementedError
        return self.submission_model.model_validate(payload).model_dump(mode="json")

    def comparison_row(self, payload: dict) -> dict:
        return payload

    def missing_documents(self, kinds_present: List[str]) -> List[str]:
        present = set(kinds_present)
        return [req.kind for req in self.document_requirements if req.required and req.kind not in present]

    def requirement(self, kind: str) -> Optional[DocumentRequirement]:
        for req in self.document_requirements:
            if req.kind == kind:
                return req
        return None

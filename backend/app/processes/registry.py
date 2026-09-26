"""Registered process types. Adding a type = a definition class + an entry here
+ a `process_types` row. Shared services do not change."""
from __future__ import annotations

from typing import Dict

from app.core.errors import Invalid
from app.processes.base import ProcessDefinition
from app.processes.rfq import RFQProcess

_DEFINITIONS: Dict[str, ProcessDefinition] = {
    RFQProcess.key: RFQProcess(),
}

# Types designed but not yet implemented; shown as "coming" in the catalogue.
PLANNED_TYPES = {
    "tender": {"he": "מכרז", "ar": "مناقصة", "en": "Tender"},
    "scholarship": {"he": "מלגה", "ar": "منحة", "en": "Scholarship"},
    "call_for_proposals": {"he": "קול קורא", "ar": "دعوة لتقديم مقترحات", "en": "Call for proposals"},
}


def get_definition(key: str) -> ProcessDefinition:
    definition = _DEFINITIONS.get(key)
    if definition is None:
        raise Invalid("process_type_unavailable", f"Process type {key!r} is not available")
    return definition


def all_definitions() -> Dict[str, ProcessDefinition]:
    return dict(_DEFINITIONS)

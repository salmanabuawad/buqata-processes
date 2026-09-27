"""The role → permission map. The single source of truth (see docs/RBAC.md).

It is synchronised into the roles/permissions tables for reporting, but no API
edits it — an administrator cannot mint a role that can read sealed content.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

PERMISSIONS: Dict[str, str] = {
    "system.configure": "Settings, integrations, process-type configuration",
    "user.manage": "Create and deactivate users",
    "role.assign": "Grant and revoke roles (never to oneself)",
    "category.manage": "Maintain the category tree",
    "template.manage": "Notification templates",
    "system_log.read": "Technical logs and delivery errors",
    "supplier.registry.read": "Browse the supplier registry",
    "supplier.registry.manage": "Add, edit, suspend and archive suppliers",
    "supplier.self": "Maintain one's own supplier profile",
    "process.read": "Process metadata, status and timeline",
    "process.read.own": "Metadata of the processes one takes part in",
    "process.create.rfq": "Create quotation requests",
    "process.create.tender": "Create tenders",
    "process.create.scholarship": "Create scholarship programs",
    "process.manage": "Edit drafts, publish, cancel",
    "process.monitor": "Distribution and fairness data",
    "opening.initiate": "Start an opening request",
    "opening.approve": "Approve an opening request",
    "submission.create": "Submit to a process one is invited to",
    "submission.read_opened": "Read opened submission content",
    "decision.record": "Record decisions",
    "protocol.generate": "Generate protocols",
    "protocol.read": "Read protocols",
    "audit.read": "Read the audit trail",
    "audit.verify": "Verify the audit hash chain",
    "committee.review": "Review assigned items",
    "scholarship.manage": "Configure scholarship programs",
    "application.create": "Apply for scholarships",
    "security_alert.receive": "Receive critical security notifications",
}

ROLES: Dict[str, dict] = {
    "system_admin": {
        "names": ("מנהל מערכת", "مدير النظام", "System administrator"),
        "business": False,
        "permissions": {
            "system.configure", "user.manage", "role.assign", "category.manage",
            "template.manage", "system_log.read", "supplier.registry.read",
            "supplier.registry.manage", "audit.verify",
        },
    },
    "procurement_manager": {
        "names": ("מנהל/ת רכש", "مدير المشتريات", "Procurement manager"),
        "business": True,
        "permissions": {
            "category.manage", "supplier.registry.read",
            "process.read", "process.create.rfq", "process.create.tender", "process.manage",
            "process.monitor", "opening.initiate", "opening.approve", "submission.read_opened",
            "decision.record", "protocol.generate", "protocol.read",
        },
    },
    # Department staff: open quotation requests and follow their own. Offers are
    # opened and decided by procurement staff the requester adds as participants.
    "requester": {
        "names": ("מבקש/ת הצעות מחיר", "طالب عروض أسعار", "Quotation requester"),
        "business": True,
        "permissions": {"process.read.own", "process.create.rfq", "process.manage"},
    },
    "tender_committee": {
        "names": ("חבר/ת ועדת מכרזים", "عضو لجنة المناقصات", "Tender committee member"),
        "business": True,
        "permissions": {
            "process.read", "process.monitor", "opening.approve", "submission.read_opened",
            "decision.record", "protocol.generate", "protocol.read", "committee.review",
        },
    },
    "scholarship_admin": {
        "names": ("רכז/ת מלגות", "منسق المنح", "Scholarship administrator"),
        "business": True,
        "permissions": {
            "process.read", "process.create.scholarship", "process.manage", "process.monitor",
            "decision.record", "protocol.generate", "protocol.read", "scholarship.manage",
        },
    },
    "scholarship_committee": {
        "names": ("חבר/ת ועדת מלגות", "عضو لجنة المنح", "Scholarship committee member"),
        "business": True,
        "permissions": {"committee.review"},
    },
    "auditor": {
        "names": ("מבקר/ת / יועמ\"ש", "مدقق / مستشار قانوني", "Auditor / legal"),
        "business": True,
        "permissions": {
            "supplier.registry.read", "process.read", "process.monitor", "protocol.read",
            "audit.read", "audit.verify", "security_alert.receive",
        },
    },
    "supplier": {
        "names": ("ספק", "مورّد", "Supplier"),
        "business": False,
        "permissions": {"supplier.self", "submission.create"},
    },
    "applicant": {
        "names": ("מבקש/ת מלגה", "مقدم طلب منحة", "Scholarship applicant"),
        "business": False,
        "permissions": {"application.create"},
    },
}


def permissions_for(role_keys) -> FrozenSet[str]:
    granted = set()
    for key in role_keys:
        role = ROLES.get(key)
        if role:
            granted |= role["permissions"]
    return frozenset(granted)


def _self_check() -> None:
    for key, role in ROLES.items():
        unknown = role["permissions"] - PERMISSIONS.keys()
        if unknown:
            raise RuntimeError(f"Role {key} references unknown permissions: {sorted(unknown)}")


_self_check()

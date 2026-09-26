"""ProtocolService — printable HTML protocols, hashed and pinned to the audit chain."""
from __future__ import annotations

from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict, Invalid, NotFound
from app.core.security import sha256_hex
from app.models import (
    AuditEvent,
    DistributionRecipient,
    DistributionSnapshot,
    NotificationDelivery,
    Notification,
    OpeningRequest,
    Process,
    ProcessVersion,
    Protocol,
    User,
)
from app.processes.registry import get_definition
from app.services import audit, authorization, evaluation, processes as process_service
from app.services import vault as vault_service
from app.services.identity import AuthContext
from app.services.notifications import format_datetime

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates")),
    autoescape=select_autoescape(["html"]),
)

LABELS = {
    "he": {
        "council": "מועצה מקומית בוקעאתא", "title": "פרוטוקול פתיחת הצעות והחלטה", "generated": "הופק",
        "generated_by": "הופק על ידי", "s_process": "פרטי ההליך", "type": "סוג הליך", "categories": "תחומים",
        "quantity": "כמות", "published": "פורסם", "deadline": "מועד אחרון להגשה", "version_hash": "טביעת גרסה מפורסמת",
        "s_distribution": "הפצה אוטומטית", "rule": "כלל הפצה",
        "rule_text": "כל הספקים הפעילים הרשומים בתחומי ההליך (כולל תחומי-על ותת-תחומים). אין אפשרות להסרה ידנית.",
        "recipients": "ספקים שהוזמנו", "delivered": "הודעות דוא\"ל שנמסרו", "failed": "מסירות שנכשלו",
        "opened_invitation": "פתחו את ההזמנה", "snapshot": "תמונת הפצה",
        "s_opening": "פתיחת תיבת ההצעות", "sealed_count": "הצעות חתומות", "opened_at": "מועד הפתיחה",
        "approver": "מאשר/ת", "decision": "החלטה", "time": "מועד", "auth": "אימות",
        "opening_note": "כל ההצעות נפתחו יחד, לאחר המועד האחרון ובהתאם למדיניות הפתיחה שהוגדרה. תקינות כל קובץ אומתה (SHA-256).",
        "s_submissions": "ההצעות שהתקבלו", "supplier": "ספק", "receipt": "מספר אישור", "submitted_at": "מועד הגשה",
        "price": "מחיר לפני מע\"מ", "vat": "מע\"מ", "total": "סה\"כ", "delivery": "אספקה", "warranty": "אחריות",
        "payment": "תנאי תשלום", "docs": "מסמכים נדרשים", "integrity": "תקינות", "complete": "מלא",
        "incomplete": "חסר", "ok": "תקין", "failed_integrity": "נכשל",
        "no_ranking": "המערכת אינה מדרגת הצעות ואינה קובעת זוכה. ההחלטה בידי בעלי הסמכות במועצה.",
        "s_decision": "החלטה", "selected": "ספק שנבחר", "reason": "נימוק", "decided_by": "מקבל/ת ההחלטה",
        "award": "בחירת ספק", "no_award": "ללא בחירה",
        "s_audit": "יומן ביקורת", "audit_events": "אירועים בהליך", "audit_head": "ראש שרשרת היומן",
        "chain": "אימות שרשרת", "chain_ok": "תקין", "chain_broken": "נמצאה פגיעה בשרשרת",
        "sign_1": "מנהל/ת רכש", "sign_2": "גזבר/ית", "sign_3": "מורשה חתימה",
        "days": "ימים", "months": "חודשים",
        "unsealed_note": "הבקשה לא נחתמה: ההצעות היו גלויות לצוות ההליך עם הגשתן, וכל צפייה נרשמה ביומן.", "early_note": "הכספת נפתחה לפני המועד האחרון; הפתיחה סגרה את ההגשה.", "manual_changes": "שינויים ידניים ברשימת התפוצה", "added": "נוסף", "removed": "הוסר", "no_manual_changes": "לא בוצעו שינויים ידניים.", 
        "footer": "מסמך זה הופק אוטומטית ממערכת ההליכים הדיגיטליים של המועצה. טביעת המסמך נשמרת ביומן הביקורת.",
    },
    "ar": {
        "council": "المجلس المحلي بقعاثا", "title": "محضر فتح العروض والقرار", "generated": "أُصدر",
        "generated_by": "أصدره", "s_process": "تفاصيل الإجراء", "type": "نوع الإجراء", "categories": "المجالات",
        "quantity": "الكمية", "published": "نُشر", "deadline": "الموعد الأخير للتقديم", "version_hash": "بصمة النسخة المنشورة",
        "s_distribution": "التوزيع التلقائي", "rule": "قاعدة التوزيع",
        "rule_text": "جميع المورّدين النشطين المسجّلين في مجالات الإجراء (بما في ذلك المجالات الأعم والفرعية). لا يمكن الإزالة يدوياً.",
        "recipients": "المورّدون المدعوون", "delivered": "رسائل بريد سُلّمت", "failed": "رسائل فشلت",
        "opened_invitation": "فتحوا الدعوة", "snapshot": "لقطة التوزيع",
        "s_opening": "فتح صندوق العروض", "sealed_count": "العروض المختومة", "opened_at": "وقت الفتح",
        "approver": "المصادِق", "decision": "القرار", "time": "الوقت", "auth": "التحقق",
        "opening_note": "فُتحت جميع العروض معاً بعد الموعد الأخير ووفق سياسة الفتح المحددة. تم التحقق من سلامة كل ملف (SHA-256).",
        "s_submissions": "العروض المستلمة", "supplier": "المورّد", "receipt": "رقم التأكيد", "submitted_at": "وقت التقديم",
        "price": "السعر قبل الضريبة", "vat": "ضريبة القيمة المضافة", "total": "المجموع", "delivery": "التوريد",
        "warranty": "الضمان", "payment": "شروط الدفع", "docs": "المستندات المطلوبة", "integrity": "السلامة",
        "complete": "مكتملة", "incomplete": "ناقصة", "ok": "سليم", "failed_integrity": "فشل",
        "no_ranking": "لا يرتّب النظام العروض ولا يحدد فائزاً. القرار بيد أصحاب الصلاحية في المجلس.",
        "s_decision": "القرار", "selected": "المورّد المختار", "reason": "التعليل", "decided_by": "متخذ القرار",
        "award": "اختيار مورّد", "no_award": "دون اختيار",
        "s_audit": "سجل التدقيق", "audit_events": "أحداث الإجراء", "audit_head": "رأس سلسلة السجل",
        "chain": "التحقق من السلسلة", "chain_ok": "سليمة", "chain_broken": "تم اكتشاف خلل في السلسلة",
        "sign_1": "مدير المشتريات", "sign_2": "أمين الصندوق", "sign_3": "صاحب حق التوقيع",
        "days": "أيام", "months": "أشهر",
        "unsealed_note": "لم يُختم الطلب: كانت العروض ظاهرة لفريق الإجراء عند تقديمها، وسُجّل كل اطلاع في السجل.", "early_note": "فُتحت الخزنة قبل الموعد الأخير؛ وأغلق الفتح باب التقديم.", "manual_changes": "تغييرات يدوية على قائمة التوزيع", "added": "أُضيف", "removed": "أُزيل", "no_manual_changes": "لم تُجرَ تغييرات يدوية.", 
        "footer": "أُنتج هذا المستند تلقائياً من نظام الإجراءات الرقمية للمجلس. بصمة المستند محفوظة في سجل التدقيق.",
    },
    "en": {
        "council": "Buq'ata Local Council", "title": "Opening and decision protocol", "generated": "Generated",
        "generated_by": "Generated by", "s_process": "Process", "type": "Type", "categories": "Categories",
        "quantity": "Quantity", "published": "Published", "deadline": "Submission deadline",
        "version_hash": "Published version fingerprint", "s_distribution": "Automatic distribution", "rule": "Rule",
        "rule_text": "Every active supplier registered in the process categories (including broader and narrower categories). No manual removal is possible.",
        "recipients": "Suppliers invited", "delivered": "E-mails delivered", "failed": "Failed deliveries",
        "opened_invitation": "Opened the invitation", "snapshot": "Distribution snapshot",
        "s_opening": "Opening of the submission box", "sealed_count": "Sealed submissions", "opened_at": "Opened at",
        "approver": "Approver", "decision": "Decision", "time": "Time", "auth": "Authentication",
        "opening_note": "All submissions were opened together, after the deadline and under the configured opening policy. Every file's integrity was verified (SHA-256).",
        "s_submissions": "Submissions received", "supplier": "Supplier", "receipt": "Receipt", "submitted_at": "Submitted",
        "price": "Price before VAT", "vat": "VAT", "total": "Total", "delivery": "Delivery", "warranty": "Warranty",
        "payment": "Payment terms", "docs": "Required documents", "integrity": "Integrity", "complete": "Complete",
        "incomplete": "Missing", "ok": "OK", "failed_integrity": "Failed",
        "no_ranking": "The system does not rank submissions or determine a winner. The decision rests with authorized council officials.",
        "s_decision": "Decision", "selected": "Selected supplier", "reason": "Reason", "decided_by": "Decided by",
        "award": "Award", "no_award": "No award",
        "s_audit": "Audit trail", "audit_events": "Events for this process", "audit_head": "Audit chain head",
        "chain": "Chain verification", "chain_ok": "Valid", "chain_broken": "Chain damage detected",
        "sign_1": "Procurement manager", "sign_2": "Treasurer", "sign_3": "Authorized signatory",
        "days": "days", "months": "months",
        "unsealed_note": "This request was not sealed: offers were visible to the process team as they arrived, and every view was logged.", "early_note": "The vault was opened before the deadline; opening closed submissions.", "manual_changes": "Manual changes to the distribution list", "added": "Added", "removed": "Removed", "no_manual_changes": "No manual changes were made.", 
        "footer": "Generated automatically by the council's digital process platform. The document fingerprint is kept in the audit trail.",
    },
}


def _money(agorot) -> str:
    if agorot is None:
        return "—"
    return f"₪{agorot / 100:,.2f}"


def generate(db: Session, ctx: AuthContext, process: Process, locale: str = "he") -> Protocol:
    authorization.require_scope(db, ctx, process, "protocol.generate")
    if locale not in LABELS:
        raise Invalid("invalid_locale", "Unsupported locale")
    if process.status in ("DRAFT", "CANCELLED") or not process_service.content_readable(db, process):
        raise Conflict("protocol_not_available", "A protocol can be generated after opening")
    t = LABELS[locale]
    definition = get_definition(process.process_type)
    version = db.get(ProcessVersion, process.current_version_id) if process.current_version_id else None
    vault_row = process_service.vault_of(db, process)
    submissions = process_service.submitted(db, process)
    sealed = definition.content_sealed(process)
    payloads = vault_service.read_payloads(vault_row, submissions, ctx.actor(), sealed=sealed)

    rows: List[dict] = []
    for s in submissions:
        p = payloads.get(s.id) or {}
        kinds = [d.kind for d in s.current_version.documents]
        rows.append({
            "supplier": s.supplier.company_name, "receipt": s.receipt_number,
            "submitted_at": format_datetime(s.submitted_at),
            "price": _money(p.get("price_before_vat_agorot")), "vat": _money(p.get("vat_agorot")),
            "total": _money(p.get("total_agorot")),
            "delivery": f"{p.get('delivery_days', '—')} {t['days']}",
            "warranty": f"{p.get('warranty_months', '—')} {t['months']}",
            "payment": p.get("payment_terms") or "—",
            "docs_complete": not definition.missing_documents(kinds),
            "integrity_ok": bool(p) and all(d.file.integrity_status == "OK" for d in s.current_version.documents),
        })

    snapshots = db.execute(select(DistributionSnapshot).where(DistributionSnapshot.process_id == process.id)
                           .order_by(DistributionSnapshot.created_at)).scalars().all()
    email_status = dict(db.execute(
        select(NotificationDelivery.status, func.count())
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .join(DistributionRecipient, DistributionRecipient.notification_id == Notification.id)
        .where(DistributionRecipient.process_id == process.id, NotificationDelivery.channel == "EMAIL")
        .group_by(NotificationDelivery.status)
    ).all())
    opened_invites = db.execute(select(func.count(DistributionRecipient.id)).where(
        DistributionRecipient.process_id == process.id, DistributionRecipient.opened_at.is_not(None))).scalar_one()

    request = db.execute(select(OpeningRequest).where(OpeningRequest.process_id == process.id,
                                                      OpeningRequest.status == "EXECUTED")).scalar_one_or_none()
    approvals = []
    if request:
        names = {u.id: u.full_name for u in db.execute(
            select(User).where(User.id.in_([a.approver_id for a in request.approvals]))).scalars()}
        for a in request.approvals:
            approvals.append({"name": names.get(a.approver_id, "—"), "decision": a.decision,
                              "at": format_datetime(a.decided_at),
                              "auth": "MFA" if a.auth_context.get("mfa") else ", ".join(a.auth_context.get("amr") or []),
                              "ip": a.client_ip})

    decision = evaluation.latest_decision(db, process)
    decision_view = None
    if decision:
        decider = db.get(User, decision.decided_by)
        decision_view = {"label": t["award"] if decision.decision_type == "AWARD" else t["no_award"],
                         "supplier": (decision.metadata_ or {}).get("supplier_name"), "reason": decision.reason,
                         "by": decider.full_name if decider else "—", "at": format_datetime(decision.decided_at)}

    from app.services.categories import breadcrumb

    chain = audit.verify_audit_chain(db)
    html = _env.get_template("protocol.html").render(
        t=t, locale=locale, process=process, kind=definition.names.get(locale, definition.key),
        categories=[breadcrumb(db, pc.category, locale) for pc in process.categories],
        published_at=format_datetime(process.published_at), deadline=format_datetime(process.submission_deadline),
        version_hash=version.content_hash if version else "—",
        distribution={"recipients": sum(s.recipient_count for s in snapshots),
                      "delivered": email_status.get("SENT", 0),
                      "failed": email_status.get("FAILED", 0) + email_status.get("DEAD", 0),
                      "opened": opened_invites,
                      "snapshots": [{"kind": s.kind, "hash": s.snapshot_hash, "count": s.recipient_count} for s in snapshots]},
        sealed=sealed, distribution_changes=_distribution_changes(db, process, locale),
        submissions=submissions, opened_at=format_datetime(vault_row.opened_at if vault_row else None),
        opened_early=bool(vault_row and vault_row.opened_at and vault_row.opened_at < process.submission_deadline),
        approvals=approvals, rows=rows, decision=decision_view,
        audit_count=db.execute(select(func.count(AuditEvent.id)).where(AuditEvent.process_id == process.id)).scalar_one(),
        audit_head=chain.head_hash, chain_valid=chain.valid,
        generated_at=format_datetime(clock.now()), generated_by=ctx.user.full_name,
    )
    protocol = Protocol(process_id=process.id, protocol_type="rfq_decision" if decision else "rfq_opening",
                        locale=locale, html=html, content_hash=sha256_hex(html.encode()),
                        audit_head_hash=chain.head_hash, generated_by=ctx.user_id, generated_at=clock.now())
    db.add(protocol)
    db.flush()
    audit.record(db, "PROTOCOL_GENERATED", ctx.actor(), process_id=process.id,
                 metadata={"protocol_id": protocol.id, "type": protocol.protocol_type, "locale": locale,
                           "content_hash": protocol.content_hash, "audit_head_hash": chain.head_hash})
    return protocol


def _distribution_changes(db: Session, process: Process, locale: str) -> List[dict]:
    from app.models import Supplier

    changes = []
    for r in db.execute(select(DistributionRecipient).where(DistributionRecipient.process_id == process.id)).scalars():
        supplier = db.get(Supplier, r.supplier_id)
        manual = (r.match_reason or {}).get("manual")
        if manual:
            changes.append({"kind": "added", "supplier": supplier.company_name, "reason": manual.get("reason", ""),
                            "at": format_datetime(r.notified_at)})
        if r.removed_at:
            changes.append({"kind": "removed", "supplier": supplier.company_name, "reason": r.removal_reason or "",
                            "at": format_datetime(r.removed_at)})
    return changes


def list_for(db: Session, ctx: AuthContext, process: Process) -> List[Protocol]:
    authorization.require(ctx, "protocol.read")
    return list(db.execute(select(Protocol).where(Protocol.process_id == process.id)
                           .order_by(Protocol.generated_at.desc())).scalars())


def get_html(db: Session, ctx: AuthContext, protocol_id) -> Protocol:
    authorization.require(ctx, "protocol.read")
    protocol = db.get(Protocol, protocol_id)
    if protocol is None:
        raise NotFound("protocol")
    audit.record(db, "PROTOCOL_VIEWED", ctx.actor(), process_id=protocol.process_id,
                 metadata={"protocol_id": protocol.id})
    return protocol

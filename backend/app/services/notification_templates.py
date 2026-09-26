"""Notification texts in Hebrew, Arabic and English.

Templates carry only non-confidential information: reference numbers, titles,
times and links. They never include prices, competitor names or file contents.
"""
from __future__ import annotations

from typing import Dict, Tuple

TEMPLATES: Dict[str, Dict[str, Tuple[str, str]]] = {
    "RFQ_INVITATION": {
        "he": (
            "בקשה חדשה להצעת מחיר בתחום שבו נרשמתם: {reference}",
            "שלום {company},\n\nמועצה מקומית בוקעאתא פרסמה בקשה להצעת מחיר התואמת את תחום הפעילות שבו נרשמתם.\n\n"
            "הליך: {reference} — {title}\nמועד אחרון להגשה: {deadline}\n\n"
            "לצפייה ולהגשת הצעה: {link}\n\nההזמנה נשלחה אוטומטית לכל הספקים הרשומים בתחום.",
        ),
        "ar": (
            "طلب عرض أسعار جديد في مجال نشاطكم: {reference}",
            "مرحباً {company}،\n\nنشر المجلس المحلي بقعاثا طلب عرض أسعار يتوافق مع مجال النشاط الذي سجّلتم فيه.\n\n"
            "الإجراء: {reference} — {title}\nالموعد الأخير للتقديم: {deadline}\n\n"
            "للاطلاع وتقديم العرض: {link}\n\nأُرسلت الدعوة تلقائياً إلى جميع المورّدين المسجّلين في هذا المجال.",
        ),
        "en": (
            "New quotation request matching your registered business category: {reference}",
            "Hello {company},\n\nBuq'ata Local Council has published a request for quotation that matches a "
            "business category you registered for.\n\nProcess: {reference} — {title}\nSubmission deadline: {deadline}\n\n"
            "View and submit: {link}\n\nThis invitation was sent automatically to every supplier registered in the category.",
        ),
    },
    "SUBMISSION_RECEIPT": {
        "he": (
            "אישור קבלת הצעה — {reference}",
            "הצעתכם להליך {reference} התקבלה ונחתמה בכספת הדיגיטלית.\n\nמספר אישור: {receipt}\nמועד הגשה: {submitted_at}\n"
            "טביעת אצבע (SHA-256): {receipt_hash}\n\nההצעה תיפתח רק לאחר המועד האחרון, יחד עם כל ההצעות האחרות.",
        ),
        "ar": (
            "تأكيد استلام العرض — {reference}",
            "تم استلام عرضكم للإجراء {reference} وختمه في الخزنة الرقمية.\n\nرقم التأكيد: {receipt}\nوقت التقديم: {submitted_at}\n"
            "البصمة (SHA-256): {receipt_hash}\n\nلن يُفتح العرض إلا بعد الموعد الأخير، مع جميع العروض الأخرى.",
        ),
        "en": (
            "Submission receipt — {reference}",
            "Your submission for {reference} was received and sealed in the digital vault.\n\nReceipt: {receipt}\n"
            "Submitted at: {submitted_at}\nFingerprint (SHA-256): {receipt_hash}\n\n"
            "It will be opened only after the deadline, together with all other submissions.",
        ),
    },
    "SUBMISSION_RECEIPT_OPEN": {
        "he": (
            "אישור קבלת הצעה — {reference}",
            "הצעתכם להליך {reference} התקבלה ונשמרה מוצפנת.\n\nמספר אישור: {receipt}\nמועד הגשה: {submitted_at}\n"
            "טביעת אצבע (SHA-256): {receipt_hash}\n\nבבקשה זו ההצעות גלויות לצוות הרכש של ההליך מרגע ההגשה.",
        ),
        "ar": (
            "تأكيد استلام العرض — {reference}",
            "تم استلام عرضكم للإجراء {reference} وحفظه مشفّراً.\n\nرقم التأكيد: {receipt}\nوقت التقديم: {submitted_at}\n"
            "البصمة (SHA-256): {receipt_hash}\n\nالعروض في هذا الطلب ظاهرة لفريق المشتريات في الإجراء من لحظة التقديم.",
        ),
        "en": (
            "Submission receipt — {reference}",
            "Your submission for {reference} was received and stored encrypted.\n\nReceipt: {receipt}\n"
            "Submitted at: {submitted_at}\nFingerprint (SHA-256): {receipt_hash}\n\n"
            "In this request offers are visible to the process's procurement team from the moment of submission.",
        ),
    },
    "VAULT_OPENED": {
        "he": (
            "תיבת ההצעות הדיגיטלית נפתחה — {reference}",
            "תיבת ההצעות הדיגיטלית ל{kind} {reference} נפתחה ביום {opened_date} בשעה {opened_time}.\n\n"
            "מספר ההצעות שנפתחו: {count}.\nכל ההצעות נפתחו יחד, לאחר המועד האחרון להגשה.",
        ),
        "ar": (
            "تم فتح صندوق العروض الرقمي — {reference}",
            "تم فتح صندوق العروض الرقمي لـ{kind} {reference} بتاريخ {opened_date} الساعة {opened_time}.\n\n"
            "عدد العروض التي فُتحت: {count}.\nفُتحت جميع العروض معاً بعد الموعد الأخير للتقديم.",
        ),
        "en": (
            "The digital submission box was opened — {reference}",
            "The digital submission box for {kind} {reference} was opened on {opened_date} at {opened_time}.\n\n"
            "Submissions opened: {count}.\nAll submissions were opened together, after the submission deadline.",
        ),
    },
    "DECISION_RECORDED": {
        "he": (
            "נרשמה החלטה בהליך {reference}",
            "המועצה רשמה החלטה בהליך {reference} — {title}.\nלפרטים ניתן לפנות לאיש הקשר של ההליך: {contact}.",
        ),
        "ar": (
            "تم تسجيل قرار في الإجراء {reference}",
            "سجّل المجلس قراراً في الإجراء {reference} — {title}.\nللتفاصيل يمكن التوجه إلى جهة الاتصال: {contact}.",
        ),
        "en": (
            "A decision was recorded for {reference}",
            "The council recorded a decision for {reference} — {title}.\nFor details contact: {contact}.",
        ),
    },
    "SUPPLIER_REGISTERED": {
        "he": (
            "ברוכים הבאים למאגר הספקים של מועצה מקומית בוקעאתא",
            "{company} נרשמה בהצלחה למאגר הספקים.\nתקבלו הזמנות אוטומטיות לכל הליך בתחומים שבחרתם: {categories}.",
        ),
        "ar": (
            "أهلاً بكم في سجل مورّدي المجلس المحلي بقعاثا",
            "تم تسجيل {company} بنجاح في سجل المورّدين.\nستصلكم دعوات تلقائية لكل إجراء في المجالات التي اخترتموها: {categories}.",
        ),
        "en": (
            "Welcome to the Buq'ata Local Council supplier registry",
            "{company} is now registered.\nYou will be invited automatically to every process in your categories: {categories}.",
        ),
    },
    "SECURITY_ALERT": {
        "he": (
            "התראת אבטחה: {event_type}",
            "נרשם אירוע אבטחה במערכת.\n\nסוג: {event_type}\nהליך: {reference}\nמועד: {occurred_at}\nמשתמש: {actor}\n"
            "מספר אירוע ביומן: {sequence}",
        ),
        "ar": (
            "تنبيه أمني: {event_type}",
            "سُجّل حدث أمني في النظام.\n\nالنوع: {event_type}\nالإجراء: {reference}\nالوقت: {occurred_at}\nالمستخدم: {actor}\n"
            "رقم الحدث في السجل: {sequence}",
        ),
        "en": (
            "Security alert: {event_type}",
            "A security event was recorded.\n\nType: {event_type}\nProcess: {reference}\nTime: {occurred_at}\nUser: {actor}\n"
            "Audit sequence: {sequence}",
        ),
    },
}

PROCESS_KIND = {
    "rfq": {"he": "בקשה להצעת מחיר", "ar": "طلب عرض الأسعار", "en": "request for quotation"},
    "tender": {"he": "מכרז", "ar": "المناقصة", "en": "tender"},
    "scholarship": {"he": "מלגה", "ar": "المنحة", "en": "scholarship"},
}


class _SafeDict(dict):
    def __missing__(self, key):
        return "—"


def render(event_type: str, locale: str, params: dict) -> Tuple[str, str]:
    template = TEMPLATES[event_type]
    subject, body = template.get(locale) or template["he"]
    safe = _SafeDict(params)
    return subject.format_map(safe), body.format_map(safe)

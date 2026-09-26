"""Demonstration data. Everything is created through the real services, so the
demo exercises the same code paths — sealing, distribution, opening, audit —
as production. All names, companies and addresses are fictional; e-mail
addresses use the reserved `.test` domain.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.rbac import permissions_for
from app.core.security import hash_password
from app.models import Category, DistributionRecipient, Process, Supplier, SupplierContact, User
from app.services import evaluation, notifications, opening, processes, protocols, submissions, suppliers
from app.services.identity import AuthContext, active_role_keys
from app.services.suppliers import default_organization, grant_role

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Buqata-Demo-2026")

STAFF = [
    ("admin@buqata.test", "רמי עמאר", ["system_admin"]),
    ("procurement@buqata.test", "סועאד אבו ג'בל", ["procurement_manager"]),
    ("procurement2@buqata.test", "וליד חלבי", ["procurement_manager"]),
    ("committee1@buqata.test", "נאדר אבו סאלח", ["tender_committee"]),
    ("committee2@buqata.test", "היפא עוידאת", ["tender_committee"]),
    ("committee3@buqata.test", "סאלם אבו עואד", ["tender_committee"]),
    ("committee4@buqata.test", "רנא מרעי", ["tender_committee"]),
    ("committee5@buqata.test", "פאדי חסון", ["tender_committee"]),
    ("scholarships@buqata.test", "לינא אבו שאהין", ["scholarship_admin"]),
    ("scholarcommittee1@buqata.test", "עמאד בריק", ["scholarship_committee"]),
    ("scholarcommittee2@buqata.test", "מונא אבו זייד", ["scholarship_committee"]),
    ("auditor@buqata.test", "עו\"ד ג'מיל ספדי", ["auditor"]),
]

# (company, slug, city, category keys, also laptops?)
SUPPLIERS = [
    # Registered at the IT root — match every IT request.
    ("מערכות מידע גולן בע\"מ", "golan-is", "מסעדה", ["it"]),
    ("טכנו-צפון פתרונות מחשוב", "techno-north", "קריית שמונה", ["it"]),
    ("אל-נור טכנולוגיות", "alnoor-tech", "בוקעאתא", ["it"]),
    ("נתיב IT שירותים", "nativ-it", "צפת", ["it"]),
    ("חרמון דיגיטל", "hermon-digital", "מג'דל שמס", ["it"]),
    # Registered at "Computers".
    ("מחשבי הגליל", "galil-computers", "כרמיאל", ["it.computers"]),
    ("קומפיוטר סנטר מסעדה", "cc-masade", "מסעדה", ["it.computers"]),
    ("ביט-טק מחשבים", "bittech", "טבריה", ["it.computers"]),
    ("מגה-מחשב", "mega-pc", "קריית שמונה", ["it.computers"]),
    ("אופק מחשבים", "ofek-pc", "חצור הגלילית", ["it.computers"]),
    ("סמארט פי.סי.", "smart-pc", "עין קנייא", ["it.computers"]),
    ("אלפא מחשוב ושירות", "alpha-computing", "נצרת", ["it.computers"]),
    ("רמת מחשבים", "ramat-pc", "קצרין", ["it.computers"]),
    # Registered at "Desktop computers" (some also at laptops).
    ("דסקטופ פלוס", "desktop-plus", "חיפה", ["it.computers.desktop", "it.computers.laptop"]),
    ("פי.סי. מאסטר", "pc-master", "עכו", ["it.computers.desktop"]),
    ("תחנות עבודה צפון", "workstations-north", "כרמיאל", ["it.computers.desktop"]),
    ("מחשבי עמק החולה", "hula-pc", "קריית שמונה", ["it.computers.desktop", "it.computers.laptop"]),
    ("אלמסאר מחשבים", "almasar-pc", "בוקעאתא", ["it.computers.desktop"]),
    ("נקסט פי.סי.", "next-pc", "טבריה", ["it.computers.desktop"]),
    ("יוניטק ציוד מחשוב", "unitech", "נהריה", ["it.computers.desktop", "it.computers.laptop"]),
    ("צפון מחשבים ותוכנה", "north-pc-soft", "צפת", ["it.computers.desktop"]),
    ("פרו-דסק", "pro-desk", "חיפה", ["it.computers.desktop"]),
    ("אינפו-סיסטמס גולן", "info-golan", "קצרין", ["it.computers.desktop"]),
    ("אלג'יל טכנולוגיה", "aljil-tech", "מג'דל שמס", ["it.computers.desktop", "it.computers.laptop"]),
    ("מחשבי הבשן", "bashan-pc", "מסעדה", ["it.computers.desktop"]),
    ("טופ-קומפ", "top-comp", "עפולה", ["it.computers.desktop"]),
    ("קו מחשב ישיר", "direct-pc", "נצרת", ["it.computers.desktop"]),
    # IT suppliers in other branches — correctly NOT invited to a desktop RFQ.
    ("רשתות הגולן", "golan-networks", "קצרין", ["it.networking"]),
    ("סייבר-שילד צפון", "cybershield", "חיפה", ["it.cyber"]),
    ("קוד פתוח פתרונות תוכנה", "open-code", "יקנעם", ["it.software"]),
    ("דפוס-טק מדפסות", "printech", "כרמיאל", ["it.printers"]),
    # Other fields.
    ("חשמל אבו שקרא", "abu-shakra-electric", "בוקעאתא", ["electric"]),
    ("אור-לד תאורה", "or-led", "חיפה", ["electric.lighting"]),
    ("תאורת הצפון", "north-lighting", "עכו", ["electric.lighting"]),
    ("שמש הגולן אנרגיה", "golan-solar", "קצרין", ["electric.solar"]),
    ("קור-אוויר מיזוג", "kor-air", "קריית שמונה", ["maintenance.ac"]),
    ("אקלים צפון", "aklim-north", "צפת", ["maintenance.ac"]),
    ("שירותי אחזקה מאוחדים", "united-maintenance", "מסעדה", ["maintenance"]),
    ("אינסטלציה רמת הגולן", "golan-plumbing", "מג'דל שמס", ["maintenance.plumbing"]),
    ("בוני הרמה", "boni-harama", "קצרין", ["construction.roads"]),
    ("שיפוצי אלכרמל", "alkarmel-renovation", "דלית אל-כרמל", ["construction.renovation"]),
    ("ריהוט משרדי נוף", "nof-furniture", "חיפה", ["office.furniture"]),
    ("משרד-פלוס ציוד", "office-plus", "כרמיאל", ["office.supplies", "office.furniture"]),
    ("הסעות רמת הגולן", "golan-transport", "בוקעאתא", ["transport"]),
    ("ניקיון זוהר", "zohar-cleaning", "עין קנייא", ["cleaning"]),
]


def _pdf(title: str) -> bytes:
    """A small, valid one-page PDF (ASCII text only)."""
    text = title.encode("ascii", "replace").decode()
    stream = f"BT /F1 14 Tf 72 740 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _ctx(db: Session, user: User) -> AuthContext:
    roles = active_role_keys(db, user.id)
    supplier_id = None
    if user.kind == "supplier":
        supplier_id = db.execute(select(SupplierContact.supplier_id).where(SupplierContact.user_id == user.id)).scalar_one()
    return AuthContext(user=user, session_id=uuid.uuid4(), role_keys=roles, permissions=permissions_for(roles),
                       amr=["seed"], ip=None, supplier_id=supplier_id)


def _cat(db: Session, key: str) -> Category:
    return db.execute(select(Category).where(Category.key == key)).scalar_one()


def _supplier_user(db: Session, slug: str) -> User:
    return db.execute(select(User).where(User.email == f"office@{slug}.test")).scalar_one()


def _publish_rfq(db, owner, *, title, description, category_keys, quantity, unit, spec, created, published,
                 deadline, delivery_days=30, reference=None, opening_mode="sealed_after_deadline") -> Process:
    with clock.frozen_at(created):
        process = processes.create(db, _ctx(db, owner), {
            "process_type": "rfq", "reference_number": reference, "title": title, "description": description,
            "category_ids": [_cat(db, k).id for k in category_keys], "submission_deadline": deadline,
            "details": {"quantity": quantity, "unit": unit, "technical_specification": spec, "opening_mode": opening_mode,
                        "expected_delivery_date": (deadline + timedelta(days=delivery_days)).date().isoformat(),
                        "additional_requirements": "יש לצרף אישור ניהול ספרים בתוקף ואישור ניכוי מס במקור."},
            "contact_name": owner.full_name, "contact_email": owner.email, "contact_phone": "04-6982000",
        })
        db.commit()
    with clock.frozen_at(published):
        processes.publish(db, _ctx(db, owner), process)
        db.commit()
        notifications.deliver_pending(db, limit=500)
    return process


def _engage(db, process: Process, *, opened: int, started: int, offers: list, rng: random.Random,
            window_start: datetime, window_end: datetime) -> None:
    """Simulate supplier behaviour: open invitations, start and submit offers.
    `offers` is a list of (price_before_vat_shekels, delivery_days, warranty_months, payment_terms)."""
    recipients = db.execute(select(DistributionRecipient).where(DistributionRecipient.process_id == process.id)
                            .order_by(DistributionRecipient.notified_at, DistributionRecipient.id)).scalars().all()
    rng.shuffle(recipients)
    span = (window_end - window_start).total_seconds()

    def moment(fraction: float) -> datetime:
        return window_start + timedelta(seconds=span * fraction)

    for i, recipient in enumerate(recipients[:opened]):
        recipient.opened_at = moment(0.05 + 0.4 * i / max(opened, 1))
    db.commit()
    for i, recipient in enumerate(recipients[:started]):
        supplier_user = db.execute(select(User).join(SupplierContact, SupplierContact.user_id == User.id)
                                   .where(SupplierContact.supplier_id == recipient.supplier_id)).scalars().first()
        ctx = _ctx(db, supplier_user)
        with clock.frozen_at(moment(0.5 + 0.2 * i / max(started, 1))):
            submissions.start(db, ctx, process)
            db.commit()
        if i < len(offers):
            price, delivery, warranty, terms = offers[i]
            supplier = db.get(Supplier, recipient.supplier_id)
            files = [("proposal", f"proposal-{supplier.company_number}.pdf",
                      _pdf(f"Quotation {process.reference_number} - supplier {supplier.company_number}"))]
            if i % 2 == 0:
                files.append(("technical_spec", "technical-specification.pdf",
                              _pdf(f"Technical specification {process.reference_number}")))
            with clock.frozen_at(moment(0.72 + 0.25 * i / max(len(offers), 1))):
                submissions.submit(db, ctx, process, {
                    "price_before_vat_agorot": int(price * 100), "delivery_days": delivery,
                    "warranty_months": warranty, "payment_terms": terms,
                    "notes": "המחיר כולל הובלה והתקנה במשרדי המועצה.",
                }, files)
                db.commit()


def _open_decide_close(db, process: Process, owner: User, *, opened_at: datetime, decided_at: datetime,
                       winner_index: int, reason: str) -> None:
    with clock.frozen_at(opened_at):
        opening.request_opening(db, _ctx(db, owner), process)
        db.commit()
        notifications.deliver_pending(db, limit=500)
    with clock.frozen_at(decided_at):
        subs = processes.submitted(db, process)
        evaluation.record_decision(db, _ctx(db, owner), process, "AWARD", subs[winner_index].id, reason)
        db.commit()
        protocols.generate(db, _ctx(db, owner), process, "he")
        db.commit()
        evaluation.close(db, _ctx(db, owner), process)
        db.commit()
        notifications.deliver_pending(db, limit=500)


def seed_demo(db: Session) -> dict:
    if db.execute(select(User.id).where(User.email == "procurement@buqata.test")).first():
        return {"skipped": True}
    rng = random.Random(2026)
    org = default_organization(db)
    now = clock.now().replace(second=0, microsecond=0)
    t0 = now - timedelta(days=60)
    password = hash_password(DEMO_PASSWORD)

    with clock.frozen_at(t0):
        staff = {}
        for email, name, roles in STAFF:
            user = User(id=uuid.uuid4(), organization_id=org.id, email=email, full_name=name, kind="staff",
                        password_hash=password, locale="he", created_at=clock.now())
            db.add(user)
            db.flush()
            for role in roles:
                grant_role(db, user, role, org.id, None, "demo seed")
            staff[email] = user
        db.commit()

    # Suppliers register over the two months before today.
    for index, (company, slug, city, cats) in enumerate(SUPPLIERS):
        registered = t0 + timedelta(hours=6 + index * 7)
        with clock.frozen_at(registered):
            suppliers.register(db, {
                "company_name": company, "company_number": f"51{index + 1:07d}", "contact_name": f"איש קשר — {company}",
                "email": f"office@{slug}.test", "phone": f"04-69{index:02d}{rng.randint(100, 999)}",
                "password": DEMO_PASSWORD, "address": f"רחוב התעשייה {index + 3}", "city": city,
                "website": f"https://{slug}.test", "description": "ספק רשום במאגר הספקים של המועצה.",
                "service_regions": [], "category_ids": [_cat(db, k).id for k in cats],
                "locale": "ar" if index % 5 == 2 else "he",
            }, None)
            db.commit()
            supplier = db.execute(select(Supplier).where(Supplier.company_number == f"51{index + 1:07d}")).scalar_one()
            if index % 3 == 0:
                expires = (now + timedelta(days=[12, 25, 200, -5, 400][index % 5])).date()
                suppliers.add_document(db, supplier, doc_type="bookkeeping", title="אישור ניהול ספרים",
                                       filename="bookkeeping.pdf", data=_pdf("Bookkeeping certificate"),
                                       issued_on=(now - timedelta(days=300)).date(), expires_on=expires,
                                       actor=_ctx(db, _supplier_user(db, slug)).actor())
                db.commit()
        notifications.deliver_pending(db, limit=500)

    owner = staff["procurement@buqata.test"]
    owner2 = staff["procurement2@buqata.test"]

    # --- Completed: LED street lighting --------------------------------------------------
    led = _publish_rfq(db, owner2, title="החלפת תאורת רחוב ל-LED בכביש הראשי",
                       description="אספקה והתקנה של 40 גופי תאורת LED לרחוב, כולל פירוק הגופים הקיימים.",
                       category_keys=["electric.lighting"], quantity=40, unit="גופי תאורה",
                       spec="גוף תאורה LED 120W, 4000K, IP66, אחריות 5 שנים לפחות, תאימות לעמודים קיימים.",
                       created=now - timedelta(days=47), published=now - timedelta(days=45),
                       deadline=now - timedelta(days=35))
    _engage(db, led, opened=3, started=3, rng=rng, window_start=now - timedelta(days=45),
            window_end=now - timedelta(days=35, hours=2),
            offers=[(118_400, 21, 60, "שוטף + 60"), (109_900, 30, 60, "שוטף + 45"), (126_000, 14, 72, "שוטף + 30")])
    _open_decide_close(db, led, owner2, opened_at=now - timedelta(days=34, hours=20),
                       decided_at=now - timedelta(days=33),
                       winner_index=1, reason="ההצעה הזולה ביותר העומדת בכל דרישות המפרט, כולל אחריות 5 שנים.")

    # --- Completed: printers ---------------------------------------------------------------
    printers = _publish_rfq(db, owner, title="רכישת 8 מדפסות משולבות למחלקת החינוך",
                            description="מדפסות לייזר משולבות (הדפסה, סריקה, צילום) לבתי הספר ולמחלקת החינוך.",
                            category_keys=["it.printers"], quantity=8, unit="יח'",
                            spec="מדפסת לייזר משולבת A4, דו-צדדי אוטומטי, רשת, 40 עמ' לדקה, כולל שירות שנתיים.",
                            created=now - timedelta(days=32), published=now - timedelta(days=30),
                            deadline=now - timedelta(days=20))
    _engage(db, printers, opened=4, started=4, rng=rng, window_start=now - timedelta(days=30),
            window_end=now - timedelta(days=20, hours=1),
            offers=[(21_600, 10, 24, "שוטף + 30"), (19_850, 14, 24, "שוטף + 60"), (23_400, 7, 36, "שוטף + 30")])
    _open_decide_close(db, printers, owner, opened_at=now - timedelta(days=19, hours=22),
                       decided_at=now - timedelta(days=18),
                       winner_index=1, reason="המחיר הנמוך ביותר; תנאי אחריות ושירות עומדים בדרישות.")

    # --- Demo RFQ: desktops, deadline passed, awaiting opening ------------------------------
    desktops = _publish_rfq(db, owner, title="רכישת 20 מחשבים נייחים", reference=f"RFQ-{now.year}-0184",
                            description="רכישת 20 עמדות מחשב נייחות עבור מחלקות המועצה, כולל מסכים והתקנה.",
                            category_keys=["it.computers.desktop"], quantity=20, unit="עמדות",
                            spec="מעבד Intel Core i5 דור 13 ומעלה או שווה ערך, 16GB RAM, SSD 512GB, Windows 11 Pro, "
                                 "מסך 24 אינץ', מקלדת ועכבר בעברית/ערבית, אחריות 3 שנים באתר.",
                            created=now - timedelta(days=9), published=now - timedelta(days=7),
                            deadline=now - timedelta(hours=2))
    _engage(db, desktops, opened=11, started=8, rng=rng, window_start=now - timedelta(days=7),
            window_end=now - timedelta(hours=3),
            offers=[(84_200, 21, 36, "שוטף + 30"), (79_900, 30, 36, "שוטף + 60"), (91_500, 14, 48, "שוטף + 30"),
                    (76_400, 45, 36, "שוטף + 90"), (82_000, 21, 36, "שוטף + 45"), (88_700, 10, 36, "שוטף + 30")])

    # --- Active: laptops ------------------------------------------------------------------------
    laptops = _publish_rfq(db, owner2, title="רכישת 35 מחשבים ניידים לבית הספר היסודי",
                           description="מחשבים ניידים לתלמידים ולצוות ההוראה, כולל תיקי נשיאה.",
                           category_keys=["it.computers.laptop"], quantity=35, unit="יח'",
                           spec="מסך 14 אינץ', 8GB RAM, SSD 256GB, סוללה 8 שעות לפחות, מקלדת תלת-לשונית.",
                           created=now - timedelta(days=4), published=now - timedelta(days=3),
                           deadline=now + timedelta(days=6), opening_mode="visible")
    _engage(db, laptops, opened=5, started=3, rng=rng, window_start=now - timedelta(days=3),
            window_end=now - timedelta(hours=1),
            offers=[(98_000, 30, 24, "שוטף + 60"), (104_500, 21, 36, "שוטף + 30")])

    # --- Active: air conditioning maintenance ---------------------------------------------------
    ac = _publish_rfq(db, owner, title="שירותי תחזוקה למזגנים במבני המועצה — 12 חודשים",
                      description="תחזוקה מונעת ותיקון תקלות ל-46 יחידות מיזוג במבני המועצה ובמתנ\"ס.",
                      category_keys=["maintenance.ac"], quantity=46, unit="יחידות מיזוג",
                      spec="שני טיפולים מונעים בשנה לכל יחידה, זמן תגובה לתקלה עד 24 שעות, כולל חלקי חילוף עד 500 ₪.",
                      created=now - timedelta(days=2), published=now - timedelta(days=1),
                      deadline=now + timedelta(days=10), opening_mode="sealed_anytime")
    _engage(db, ac, opened=1, started=0, rng=rng, window_start=now - timedelta(days=1),
            window_end=now - timedelta(hours=1), offers=[])

    # --- Draft ------------------------------------------------------------------------------------
    with clock.frozen_at(now - timedelta(hours=5)):
        processes.create(db, _ctx(db, owner), {
            "process_type": "rfq", "title": "רכישת ריהוט משרדי לאגף ההנדסה",
            "description": "12 עמדות עבודה ארגונומיות וכיסאות.", "category_ids": [_cat(db, "office.furniture").id],
            "submission_deadline": now + timedelta(days=14),
            "details": {"quantity": 12, "unit": "עמדות", "technical_specification": "שולחן מתכוונן חשמלי 160x80, כיסא ארגונומי."},
            "contact_name": owner.full_name, "contact_email": owner.email,
        })
        db.commit()

    notifications.deliver_pending(db, limit=1000)
    return {"skipped": False, "desktop_rfq": str(desktops.id), "suppliers": len(SUPPLIERS)}


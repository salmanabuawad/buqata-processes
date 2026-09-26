"""Baseline data every installation needs. Idempotent: safe on every deploy."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Organization, ProcessType
from app.processes.registry import PLANNED_TYPES, all_definitions
from app.services import admin, categories
from app.services.audit import Actor

CATEGORY_TREE = [
    ("it", "מחשוב", "حوسبة", "IT & computing", [
        ("it.computers", "מחשבים", "حواسيب", "Computers", [
            ("it.computers.desktop", "מחשבים נייחים", "حواسيب مكتبية", "Desktop computers", []),
            ("it.computers.laptop", "מחשבים ניידים", "حواسيب محمولة", "Laptops", []),
            ("it.computers.tablet", "טאבלטים", "أجهزة لوحية", "Tablets", []),
        ]),
        ("it.networking", "תקשורת ורשתות", "الشبكات والاتصالات", "Networking", []),
        ("it.cyber", "סייבר ואבטחת מידע", "الأمن السيبراني", "Cybersecurity", []),
        ("it.printers", "מדפסות וציוד היקפי", "الطابعات والملحقات", "Printers & peripherals", []),
        ("it.software", "תוכנה", "برمجيات", "Software", []),
    ]),
    ("electric", "חשמל", "كهرباء", "Electricity", [
        ("electric.install", "עבודות חשמל", "أعمال كهربائية", "Electrical installations", []),
        ("electric.lighting", "תאורה", "إنارة", "Lighting", []),
        ("electric.solar", "אנרגיה סולארית", "طاقة شمسية", "Solar energy", []),
    ]),
    ("maintenance", "תחזוקה", "صيانة", "Maintenance", [
        ("maintenance.ac", "מיזוג אוויר", "تكييف الهواء", "Air conditioning", []),
        ("maintenance.plumbing", "אינסטלציה", "تمديدات صحية", "Plumbing", []),
        ("maintenance.building", "תחזוקת מבנים", "صيانة المباني", "Building maintenance", []),
    ]),
    ("construction", "בנייה ותשתיות", "بناء وبنى تحتية", "Construction & infrastructure", [
        ("construction.roads", "כבישים ופיתוח", "طرق وتطوير", "Roads & development", []),
        ("construction.renovation", "שיפוצים", "ترميمات", "Renovation", []),
    ]),
    ("engineering", "הנדסה ותכנון", "هندسة وتخطيط", "Engineering & planning", []),
    ("transport", "הסעות ותחבורה", "نقل ومواصلات", "Transportation", []),
    ("office", "ציוד משרדי", "معدات مكتبية", "Office equipment", [
        ("office.furniture", "ריהוט", "أثاث", "Furniture", []),
        ("office.supplies", "ציוד מתכלה", "لوازم مكتبية", "Office supplies", []),
    ]),
    ("consulting", "ייעוץ ושירותים מקצועיים", "استشارات وخدمات مهنية", "Consulting & professional services", []),
    ("cleaning", "ניקיון", "نظافة", "Cleaning", []),
    ("gardening", "גינון ונוף", "بستنة وتنسيق حدائق", "Gardening & landscaping", []),
    ("events", "אירועים והפקות", "فعاليات وإنتاج", "Events & productions", []),
    ("printing", "דפוס ופרסום", "طباعة ونشر", "Printing & publishing", []),
]


def _seed_categories(db: Session) -> None:
    system = Actor.system()

    def walk(nodes, parent_id, order_base=0):
        for index, (key, he, ar, en, children) in enumerate(nodes):
            existing = db.execute(select(Category).where(Category.key == key)).scalar_one_or_none()
            if existing is None:
                existing = categories.create(db, system, key=key, name_he=he, name_ar=ar, name_en=en,
                                             parent_id=parent_id, sort_order=order_base + index)
            walk(children, existing.id)

    walk(CATEGORY_TREE, None)


def seed_baseline(db: Session) -> None:
    admin.sync_rbac(db)
    if db.execute(select(Organization).where(Organization.slug == "buqata")).scalar_one_or_none() is None:
        db.add(Organization(slug="buqata", name_he="מועצה מקומית בוקעאתא", name_ar="المجلس المحلي بقعاثا",
                            name_en="Buq'ata Local Council"))
    for key, definition in all_definitions().items():
        row = db.get(ProcessType, key)
        if row is None:
            row = ProcessType(key=key)
            db.add(row)
        row.name_he, row.name_ar, row.name_en = definition.names["he"], definition.names["ar"], definition.names["en"]
        row.is_enabled = True
        row.default_config = {"opening_rules": definition.default_opening_rules,
                              "required_approvals": definition.default_required_approvals}
    for key, names in PLANNED_TYPES.items():
        if db.get(ProcessType, key) is None:
            db.add(ProcessType(key=key, name_he=names["he"], name_ar=names["ar"], name_en=names["en"],
                               is_enabled=False, default_config={}))
    db.flush()
    if db.execute(select(Category.id).limit(1)).first() is None:
        _seed_categories(db)
    db.commit()

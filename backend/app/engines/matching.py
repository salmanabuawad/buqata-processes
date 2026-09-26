"""Supplier ↔ process category matching. Pure logic.

Paths are materialised as "/<root id>/<child id>/.../". Two categories are on
the same branch when one path is a prefix of the other.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class CategoryRef:
    id: str
    path: str


@dataclass(frozen=True)
class Match:
    supplier_category_id: str
    process_category_id: str
    relation: str  # exact | supplier_broader | supplier_narrower


def relation(supplier_cat: CategoryRef, process_cat: CategoryRef) -> Optional[str]:
    if supplier_cat.id == process_cat.id:
        return "exact"
    if process_cat.path.startswith(supplier_cat.path):
        return "supplier_broader"
    if supplier_cat.path.startswith(process_cat.path):
        return "supplier_narrower"
    return None


def match_supplier(
    supplier_categories: Sequence[CategoryRef],
    process_categories: Sequence[CategoryRef],
    supplier_regions: Iterable[str] = (),
    process_regions: Iterable[str] = (),
) -> List[Match]:
    process_regions = set(process_regions or ())
    if process_regions and not (set(supplier_regions or ()) & process_regions):
        return []
    matches = []
    for sc in supplier_categories:
        for pc in process_categories:
            rel = relation(sc, pc)
            if rel:
                matches.append(Match(sc.id, pc.id, rel))
    return matches

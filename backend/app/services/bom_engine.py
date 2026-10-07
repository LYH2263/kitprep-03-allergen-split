"""Central kitchen BOM explode: order lines × BOM qty, merge ingredients, shortage = need - stock."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

@dataclass
class NeedLine:
    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    unit: str
    need_qty: float
    stock_qty: float
    shortage: float
    is_allergen: bool = False
    occupied_qty: float = 0.0

def explode_and_merge(
    order_lines: list[dict],
    bom_lines: list[dict],
    ingredients: dict[int, dict],
) -> list[NeedLine]:
    """order_lines: dish_id, portions; bom_lines: dish_id, ingredient_id, qty_per_portion."""
    need: dict[int, float] = {}
    for ol in order_lines:
        for bl in bom_lines:
            if bl["dish_id"] != ol["dish_id"]:
                continue
            need[bl["ingredient_id"]] = need.get(bl["ingredient_id"], 0.0) + ol["portions"] * bl["qty_per_portion"]
    lines: list[NeedLine] = []
    for iid, qty in sorted(need.items()):
        ing = ingredients[iid]
        stock = float(ing.get("stock_qty", 0))
        shortage = max(0.0, qty - stock)
        lines.append(NeedLine(
            ingredient_id=iid,
            ingredient_code=ing["code"],
            ingredient_name=ing["name"],
            unit=ing.get("unit", ""),
            need_qty=round(qty, 3),
            stock_qty=round(stock, 3),
            shortage=round(shortage, 3),
            is_allergen=bool(ing.get("is_allergen", False)),
            occupied_qty=round(min(qty, stock), 3),
        ))
    return lines

def split_shortages(lines: list[NeedLine]) -> tuple[list[NeedLine], list[NeedLine]]:
    """Partition shortage lines into (main_book, allergen_book).

    Disjoint by construction: an allergen shortage can only land in the allergen
    book, never the main book. Returns empty lists (never None) so both books
    always exist together.
    """
    short = [l for l in lines if l.shortage > 0]
    return (
        [l for l in short if not l.is_allergen],
        [l for l in short if l.is_allergen],
    )

def compute_fingerprint(order_id: int, lines: list[NeedLine]) -> str:
    """Stable identity of a generation.

    Covers order id, the merged (need, stock) snapshot and allergen flags — all
    already rounded to 3 decimals. Any change in order/BOM/stock/flags yields a
    different fingerprint (a new run); an unchanged world yields the same run
    even when generated concurrently from two pages.
    """
    payload = {
        "order_id": order_id,
        "ingredients": sorted(
            [l.ingredient_id, l.need_qty, l.stock_qty, bool(l.is_allergen)]
            for l in lines
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def result_to_dict(lines: list[NeedLine]) -> dict:
    main_lines, allergen_lines = split_shortages(lines)
    return {
        "prep_lines": [asdict(l) for l in lines],
        "shortages": [asdict(l) for l in lines if l.shortage > 0],
        "main_shortages": [asdict(l) for l in main_lines],
        "allergen_shortages": [asdict(l) for l in allergen_lines],
        "stats": {
            "ingredient_count": len(lines),
            "shortage_count": sum(1 for l in lines if l.shortage > 0),
            "total_shortage_qty": round(sum(l.shortage for l in lines), 3),
            "main_count": len(main_lines),
            "allergen_count": len(allergen_lines),
        },
    }

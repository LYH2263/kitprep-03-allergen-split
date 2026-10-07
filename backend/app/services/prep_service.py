"""Atomic prep-run generation with two physical shortage books and an occupation ledger.

One transaction, one commit:
  order row lock (FOR UPDATE) → snapshot → fingerprint → insert prep run +
  main book + allergen book + occupation lines → bump ingredients.occupied_qty
  → flush → invariant assertions → commit.

Any split/occupation invariant violation raises LedgerSplitError BEFORE commit;
the caller rolls back so the run, both books and the occupation column revert
together. stock_qty (结存) is never written.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import (
    AllergenShortageLine,
    BomLine,
    Ingredient,
    KitchenOrder,
    MainShortageLine,
    OccupationLine,
    OrderLine,
    PrepRun,
)
from app.services import bom_engine
from app.services.bom_engine import NeedLine, compute_fingerprint, explode_and_merge


class OrderNotFoundError(Exception):
    pass


class LedgerSplitError(Exception):
    """分册/占用一致性校验失败。与结存无关 —— 消息中禁止出现库存不足字样。"""


# --------------------------------------------------------------------------- #
# serialization
# --------------------------------------------------------------------------- #

def _shortage_row_dict(r) -> dict:
    return {
        "ingredient_id": r.ingredient_id,
        "ingredient_code": r.ingredient_code,
        "ingredient_name": r.ingredient_name,
        "unit": r.unit,
        "need_qty": r.need_qty,
        "stock_qty": r.stock_qty,
        "occupied_qty": r.occupied_qty,
        "shortage": r.shortage_qty,
    }


def _book_rows(db: Session, model, run_id: int) -> list:
    return db.scalars(
        select(model).where(model.run_id == run_id).order_by(model.id)
    ).all()


def serialize_run(db: Session, run: PrepRun) -> dict:
    """Build the API payload from the physical books (prep sheet from frozen JSON)."""
    main = [_shortage_row_dict(r) for r in _book_rows(db, MainShortageLine, run.id)]
    allergen = [_shortage_row_dict(r) for r in _book_rows(db, AllergenShortageLine, run.id)]
    stored = json.loads(run.result_json or "{}")
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "fingerprint": run.fingerprint,
        "order": stored.get("order"),
        "prep_lines": stored.get("prep_lines", []),
        "main_shortages": main,
        "allergen_shortages": allergen,
        "shortages": main + allergen,
        "stats": {
            "ingredient_count": len(stored.get("prep_lines", [])),
            "shortage_count": len(main) + len(allergen),
            "total_shortage_qty": round(sum(r["shortage"] for r in main + allergen), 3),
            "main_count": len(main),
            "allergen_count": len(allergen),
        },
    }


def empty_payload(order: KitchenOrder | None) -> dict:
    order_info = (
        {"id": order.id, "code": order.code, "outlet": order.outlet} if order else None
    )
    return {
        "id": None,
        "created_at": None,
        "fingerprint": None,
        "order": order_info,
        "prep_lines": [],
        "main_shortages": [],
        "allergen_shortages": [],
        "shortages": [],
        "stats": {
            "ingredient_count": 0,
            "shortage_count": 0,
            "total_shortage_qty": 0,
            "main_count": 0,
            "allergen_count": 0,
        },
    }


def latest_payload(db: Session, order_id: int) -> dict:
    """Read-only: newest run for the order, or an empty skeleton. Never generates."""
    order = db.get(KitchenOrder, order_id)
    run = db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).first()
    if not run:
        return empty_payload(order)
    return serialize_run(db, run)


def shortages_payload(db: Session, order_id: int) -> dict:
    """Read-only view of the two physical books of the latest run."""
    run = db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).first()
    if not run:
        return {
            "order_id": order_id,
            "run_id": None,
            "main_shortages": [],
            "allergen_shortages": [],
            "stats": empty_payload(None)["stats"],
        }
    payload = serialize_run(db, run)
    return {
        "order_id": order_id,
        "run_id": run.id,
        "main_shortages": payload["main_shortages"],
        "allergen_shortages": payload["allergen_shortages"],
        "stats": payload["stats"],
    }


# --------------------------------------------------------------------------- #
# generation
# --------------------------------------------------------------------------- #

def _snapshot(db: Session, order_id: int):
    order = db.scalar(
        select(KitchenOrder).where(KitchenOrder.id == order_id).with_for_update()
    )
    if not order:
        raise OrderNotFoundError(str(order_id))
    ols = [
        {"dish_id": l.dish_id, "portions": l.portions}
        for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    ]
    bom = [
        {"dish_id": b.dish_id, "ingredient_id": b.ingredient_id,
         "qty_per_portion": b.qty_per_portion}
        for b in db.scalars(select(BomLine)).all()
    ]
    ing_objs = {i.id: i for i in db.scalars(select(Ingredient)).all()}
    ings = {
        iid: {"code": i.code, "name": i.name, "unit": i.unit,
              "stock_qty": i.stock_qty, "is_allergen": i.is_allergen}
        for iid, i in ing_objs.items()
    }
    return order, ols, bom, ings, ing_objs


def _make_shortage_row(model, run_id: int, l: NeedLine):
    return model(
        run_id=run_id,
        ingredient_id=l.ingredient_id,
        ingredient_code=l.ingredient_code,
        ingredient_name=l.ingredient_name,
        unit=l.unit,
        need_qty=l.need_qty,
        stock_qty=l.stock_qty,
        occupied_qty=l.occupied_qty,
        shortage_qty=l.shortage,
    )


def _assert_invariants(
    db: Session,
    run_id: int,
    lines: list[NeedLine],
    main_lines: list[NeedLine],
    allergen_lines: list[NeedLine],
    before_occupied: dict[int, float],
    before_stock: dict[int, float],
) -> None:
    """Re-query the physical tables and verify the split + occupation landed correctly.

    Raises LedgerSplitError (never a stock-insufficient error) on any mismatch.
    """
    problems: list[str] = []

    main_rows = _book_rows(db, MainShortageLine, run_id)
    allergen_rows = _book_rows(db, AllergenShortageLine, run_id)
    occ_rows = db.scalars(
        select(OccupationLine).where(OccupationLine.run_id == run_id)
    ).all()

    expected_short = {l.ingredient_id for l in lines if l.shortage > 0}
    flagged = {l.ingredient_id for l in lines if l.is_allergen}
    m_ids = {r.ingredient_id for r in main_rows}
    a_ids = {r.ingredient_id for r in allergen_rows}

    # 1. partition: disjoint, complete, no leakage in either direction
    if m_ids & a_ids:
        problems.append(f"同一原料同时进入主贴与专册: {sorted(m_ids & a_ids)}")
    if m_ids | a_ids != expected_short:
        problems.append(
            f"两本并集与缺料集合不一致: books={sorted(m_ids | a_ids)} "
            f"short={sorted(expected_short)}"
        )
    if a_ids != (expected_short & flagged):
        problems.append(
            f"专册内容与含敏缺料不匹配: allergen_book={sorted(a_ids)} "
            f"expected={sorted(expected_short & flagged)}"
        )
    if m_ids != (expected_short - flagged):
        problems.append(
            f"主贴混入含敏行或漏行: main_book={sorted(m_ids)} "
            f"expected={sorted(expected_short - flagged)}"
        )

    # 2. per-row quantities (books)
    by_id = {l.ingredient_id: l for l in lines}
    for r in list(main_rows) + list(allergen_rows):
        l = by_id.get(r.ingredient_id)
        if l is None or r.shortage_qty <= 0:
            problems.append(f"台账行缺料数非法: ingredient={r.ingredient_id}")
            continue
        if round(r.shortage_qty, 3) != round(max(0.0, l.need_qty - l.stock_qty), 3):
            problems.append(f"台账缺料数与 need-stock 不符: ingredient={r.ingredient_id}")
        if round(r.occupied_qty, 3) != round(min(l.need_qty, l.stock_qty), 3):
            problems.append(f"台账占用数与 min(need,stock) 不符: ingredient={r.ingredient_id}")

    # 3. occupation ledger covers every needed ingredient exactly once
    occ_by_ing = {r.ingredient_id: r for r in occ_rows}
    if set(occ_by_ing) != {l.ingredient_id for l in lines}:
        problems.append("占用台账未覆盖全部需求原料（两本未一起落库）")
    for iid, r in occ_by_ing.items():
        l = by_id[iid]
        if round(r.occupied_qty, 3) != round(min(l.need_qty, l.stock_qty), 3):
            problems.append(f"占用台账数量不符: ingredient={iid}")

    # 4. cumulative occupied_qty delta matches this run's ledger; stock untouched
    for l in lines:
        new_occ = db.scalar(
            select(Ingredient.occupied_qty).where(Ingredient.id == l.ingredient_id)
        )
        delta = round((new_occ or 0.0) - before_occupied[l.ingredient_id], 3)
        if delta != round(occ_by_ing[l.ingredient_id].occupied_qty, 3):
            problems.append(
                f"占用列增量与台账对不上: ingredient={l.ingredient_id} "
                f"delta={delta} ledger={occ_by_ing[l.ingredient_id].occupied_qty}"
            )
        stock_now = db.scalar(
            select(Ingredient.stock_qty).where(Ingredient.id == l.ingredient_id)
        )
        if round(stock_now, 6) != round(before_stock[l.ingredient_id], 6):
            problems.append(f"结存在生成时被改动: ingredient={l.ingredient_id}")

    if problems:
        raise LedgerSplitError("；".join(problems[:5]))


def generate_prep_run(db: Session, order_id: int) -> dict:
    order, ols, bom, ings, ing_objs = _snapshot(db, order_id)
    lines = explode_and_merge(ols, bom, ings)
    main_lines, allergen_lines = bom_engine.split_shortages(lines)
    fingerprint = compute_fingerprint(order_id, lines)

    # unchanged world (also the loser of a same-order race) → the one shared set
    existing = db.scalar(select(PrepRun).where(PrepRun.fingerprint == fingerprint))
    if existing:
        return serialize_run(db, existing)

    before_occupied = {iid: float(i.occupied_qty or 0.0) for iid, i in ing_objs.items()}
    before_stock = {iid: float(i.stock_qty or 0.0) for iid, i in ing_objs.items()}

    try:
        result = bom_engine.result_to_dict(lines)
        result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
        run = PrepRun(
            order_id=order_id,
            created_at=datetime.utcnow(),
            result_json=json.dumps(result, ensure_ascii=False),
            fingerprint=fingerprint,
        )
        db.add(run)
        db.flush()  # get run.id; still inside the open transaction

        for l in main_lines:
            db.add(_make_shortage_row(MainShortageLine, run.id, l))
        for l in allergen_lines:
            db.add(_make_shortage_row(AllergenShortageLine, run.id, l))
        for l in lines:
            db.add(OccupationLine(
                run_id=run.id,
                ingredient_id=l.ingredient_id,
                need_qty=l.need_qty,
                occupied_qty=l.occupied_qty,
            ))
            # 记占用，不动结存
            ing_objs[l.ingredient_id].occupied_qty = (
                before_occupied[l.ingredient_id] + l.occupied_qty
            )

        db.flush()
        _assert_invariants(
            db, run.id, lines, main_lines, allergen_lines,
            before_occupied, before_stock,
        )
        db.commit()
    except LedgerSplitError:
        # 主贴、专册、占用列整次退回
        db.rollback()
        raise
    except IntegrityError:
        # unique-fingerprint race (SQLite: FOR UPDATE is a no-op) → winner's run
        db.rollback()
        winner = db.scalar(select(PrepRun).where(PrepRun.fingerprint == fingerprint))
        if winner is None:
            raise
        return serialize_run(db, winner)

    db.refresh(run)
    return serialize_run(db, run)

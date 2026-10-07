import os

import pytest
from sqlalchemy import func, select

from app.models.models import (
    AllergenShortageLine,
    Ingredient,
    MainShortageLine,
    OccupationLine,
    PrepRun,
)
from app.services import bom_engine


SEEDED_OCC = {  # ingredient code -> min(need, stock) for KO-0901
    "I-PR": 8.0, "I-EG": 3.0, "I-CK": 5.0, "I-RC": 10.5,
    "I-ND": 4.0, "I-SC": 1.0, "I-OL": 1.5,
}
MAIN_SHORT_CODES = {"I-PR", "I-EG", "I-CK", "I-ND", "I-OL"}
ALLERGEN_SHORT_CODES = {"I-SC"}


def _ing_map(db):
    return {i.code: i for i in db.scalars(select(Ingredient)).all()}


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model)) or 0


def _codes(rows):
    return {r["ingredient_code"] for r in rows}


# --------------------------------------------------------------------------- #
def test_generate_splits_books_records_occupation_keeps_stock(client, SessionFactory):
    resp = client.post("/api/prep/run?order_id=1")
    assert resp.status_code == 200
    body = resp.json()
    assert _codes(body["main_shortages"]) == MAIN_SHORT_CODES
    assert _codes(body["allergen_shortages"]) == ALLERGEN_SHORT_CODES
    # 含敏行只进专册，主贴禁止再出现
    assert "I-SC" not in _codes(body["main_shortages"])
    assert body["stats"]["main_count"] == 5 and body["stats"]["allergen_count"] == 1

    s = SessionFactory()
    try:
        assert _count(s, PrepRun) == 1
        assert _count(s, MainShortageLine) == 5
        assert _count(s, AllergenShortageLine) == 1
        # 占用台账覆盖全部 7 种需求原料
        occ_rows = s.scalars(select(OccupationLine)).all()
        assert {r.ingredient_id for r in occ_rows} == {i.id for i in _ing_map(s).values()}
        # 占用列 = min(need, stock)；结存逐字节不变（仍为种子值）
        seeded_stock = {
            "I-PR": 8.0, "I-EG": 3.0, "I-CK": 5.0, "I-RC": 20.0,
            "I-ND": 4.0, "I-SC": 1.0, "I-OL": 1.5,
        }
        for code, ing in _ing_map(s).items():
            assert round(ing.occupied_qty, 3) == SEEDED_OCC[code]
            assert round(ing.stock_qty, 6) == round(seeded_stock[code], 6)
    finally:
        s.close()


def test_inventory_exposes_flag_occupation_available(client, SessionFactory):
    client.post("/api/prep/run?order_id=1")
    rows = {r["code"]: r for r in client.get("/api/inventory").json()}
    sc = rows["I-SC"]
    assert sc["is_allergen"] is True
    assert sc["occupied_qty"] == 1.0
    assert sc["available_qty"] == 0.0  # 结存 1.0 - 占用 1.0，结存本身没动
    assert rows["I-RC"]["available_qty"] == round(20.0 - 10.5, 3)


def test_patch_allergen_flag_persists(client, SessionFactory):
    ings = _ing_map_shared(SessionFactory)
    resp = client.patch(f"/api/inventory/{ings['I-EG']}", json={"is_allergen": True})
    assert resp.status_code == 200 and resp.json()["is_allergen"] is True
    s = SessionFactory()
    try:
        assert s.get(Ingredient, ings["I-EG"]).is_allergen is True
    finally:
        s.close()


def _ing_map_shared(SessionFactory):
    s = SessionFactory()
    try:
        return {i.code: i.id for i in s.scalars(select(Ingredient)).all()}
    finally:
        s.close()


def test_no_flag_allergen_book_empty_all_in_main(client, db_session):
    sc = _ing_map(db_session)["I-SC"]
    sc.is_allergen = False
    db_session.commit()

    body = client.post("/api/prep/run?order_id=1").json()
    assert body["allergen_shortages"] == []
    assert _codes(body["main_shortages"]) == MAIN_SHORT_CODES | ALLERGEN_SHORT_CODES
    assert body["stats"]["allergen_count"] == 0


def test_flagged_but_sufficient_stock_allergen_book_empty(client, db_session):
    sc = _ing_map(db_session)["I-SC"]
    sc.stock_qty = 5.0  # need 1.75, no shortage
    db_session.commit()

    body = client.post("/api/prep/run?order_id=1").json()
    assert body["allergen_shortages"] == []
    assert body["id"] is not None
    assert _codes(body["main_shortages"]) == MAIN_SHORT_CODES


def test_split_violation_rolls_back_run_both_books_and_occupation(
    client, SessionFactory, monkeypatch
):
    def bad_split(lines):
        short = [l for l in lines if l.shortage > 0]
        return short, short  # 同一批行两边都记 —— 必须整次失败

    monkeypatch.setattr(bom_engine, "split_shortages", bad_split)

    resp = client.post("/api/prep/run?order_id=1")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "LEDGER_SPLIT_VIOLATION"
    msg = detail["message"]
    assert "库存不足" not in msg and "结存不够" not in msg

    s = SessionFactory()
    try:
        assert _count(s, PrepRun) == 0
        assert _count(s, MainShortageLine) == 0
        assert _count(s, AllergenShortageLine) == 0
        assert _count(s, OccupationLine) == 0
        # 占用列全部退回
        assert all((i.occupied_qty or 0.0) == 0.0 for i in s.scalars(select(Ingredient)).all())
    finally:
        s.close()


def test_duplicate_generation_returns_same_run_occupation_once(client, SessionFactory):
    first = client.post("/api/prep/run?order_id=1").json()
    second = client.post("/api/prep/run?order_id=1").json()
    assert first["id"] == second["id"]
    assert first["fingerprint"] == second["fingerprint"]

    s = SessionFactory()
    try:
        assert _count(s, PrepRun) == 1
        run_id = first["id"]
        assert _count(s, OccupationLine) == 7  # 不是 14
        for code, ing in _ing_map(s).items():
            assert round(ing.occupied_qty, 3) == SEEDED_OCC[code]  # 没有翻倍
        assert _count(s, MainShortageLine) == 5
        assert _count(s, AllergenShortageLine) == 1
        # 同一套两本账
        assert s.scalar(select(func.count()).select_from(
            MainShortageLine).where(MainShortageLine.run_id == run_id)) == 5
    finally:
        s.close()


def test_flag_change_creates_new_run_old_run_frozen(client, SessionFactory, db_session):
    first = client.post("/api/prep/run?order_id=1").json()
    old_id = first["id"]

    egg = _ing_map(db_session)["I-EG"]
    egg.is_allergen = True  # 改完标记再生成按新标记拆
    db_session.commit()

    second = client.post("/api/prep/run?order_id=1").json()
    assert second["id"] != old_id
    assert _codes(second["allergen_shortages"]) == {"I-SC", "I-EG"}
    assert "I-EG" not in _codes(second["main_shortages"])

    s = SessionFactory()
    try:
        old_allergen = s.scalars(
            select(AllergenShortageLine).where(AllergenShortageLine.run_id == old_id)
        ).all()
        # 已按旧标记落下的单禁止改字
        assert {r.ingredient_code for r in old_allergen} == {"I-SC"}
        old_main = s.scalars(
            select(MainShortageLine).where(MainShortageLine.run_id == old_id)
        ).all()
        assert {r.ingredient_code for r in old_main} == MAIN_SHORT_CODES
    finally:
        s.close()


def test_latest_is_read_only_and_empty_when_never_generated(client, SessionFactory):
    body = client.get("/api/prep/latest?order_id=1").json()
    assert body["id"] is None
    assert body["main_shortages"] == [] and body["allergen_shortages"] == []
    s = SessionFactory()
    try:
        assert _count(s, PrepRun) == 0  # GET 没有懒生成
    finally:
        s.close()


def test_shortages_legacy_run_without_ledger_rows_returns_empty(client, db_session):
    db_session.add(PrepRun(order_id=1, result_json="{}", fingerprint=None))
    db_session.commit()
    resp = client.get("/api/prep/shortages?order_id=1")
    assert resp.status_code == 200
    assert resp.json()["main_shortages"] == []
    assert resp.json()["allergen_shortages"] == []


def test_genuine_shortage_is_not_an_error(client):
    resp = client.post("/api/prep/run?order_id=1")
    assert resp.status_code == 200
    rows = resp.json()["main_shortages"]
    pork = next(r for r in rows if r["ingredient_code"] == "I-PR")
    assert pork["shortage"] == 2.0  # need 10 - stock 8, 缺料是正常结果不是错误


def test_generate_missing_order_404(client):
    assert client.post("/api/prep/run?order_id=999").status_code == 404


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="并发行锁验证需要 Postgres；设置 TEST_DATABASE_URL（已建表+seed）后运行",
)
def test_concurrent_generation_single_shared_run():  # pragma: no cover
    import threading
    from sqlalchemy import create_engine as ce
    from sqlalchemy.orm import sessionmaker as sm

    from app.services.prep_service import generate_prep_run

    eng = ce(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    Factory = sm(bind=eng, autocommit=False, autoflush=False)
    results, barrier = [], threading.Barrier(2)

    def worker():
        s = Factory()
        barrier.wait()
        try:
            results.append(generate_prep_run(s, 1)["id"])
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results[0] == results[1]

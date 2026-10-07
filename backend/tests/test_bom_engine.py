from app.services.bom_engine import (
    compute_fingerprint,
    explode_and_merge,
    split_shortages,
)

def _ings(stock_a=1.0, allergen_a=False, stock_b=5.0, allergen_b=False):
    return {
        1: {"code": "A", "name": "肉", "unit": "kg", "stock_qty": stock_a,
            "is_allergen": allergen_a},
        2: {"code": "B", "name": "米", "unit": "kg", "stock_qty": stock_b,
            "is_allergen": allergen_b},
    }

def test_explode_merge():
    order_lines = [{"dish_id": 1, "portions": 10}, {"dish_id": 2, "portions": 5}]
    bom = [
        {"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 0.2},
        {"dish_id": 1, "ingredient_id": 2, "qty_per_portion": 0.1},
        {"dish_id": 2, "ingredient_id": 1, "qty_per_portion": 0.3},
    ]
    lines = explode_and_merge(order_lines, bom, _ings())
    by_id = {l.ingredient_id: l for l in lines}
    assert by_id[1].need_qty == 3.5  # 10*0.2 + 5*0.3
    assert by_id[1].shortage == 2.5
    assert by_id[2].need_qty == 1.0
    assert by_id[2].shortage == 0.0

def test_no_negative_shortage():
    order_lines = [{"dish_id": 1, "portions": 1}]
    bom = [{"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 1.0}]
    ings = {1: {"code": "A", "name": "油", "unit": "L", "stock_qty": 10.0}}
    lines = explode_and_merge(order_lines, bom, ings)
    assert lines[0].shortage == 0.0

def test_occupied_is_min_of_need_and_stock():
    order_lines = [{"dish_id": 1, "portions": 10}]
    bom = [
        {"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 0.2},  # need 2.0, stock 1.0 -> occ 1.0
        {"dish_id": 1, "ingredient_id": 2, "qty_per_portion": 0.1},  # need 1.0, stock 5.0 -> occ 1.0
    ]
    by_id = {l.ingredient_id: l for l in explode_and_merge(order_lines, bom, _ings())}
    assert by_id[1].occupied_qty == 1.0
    assert by_id[2].occupied_qty == 1.0

def test_allergen_flag_propagates():
    order_lines = [{"dish_id": 1, "portions": 1}]
    bom = [{"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 1.0}]
    lines = explode_and_merge(order_lines, bom, _ings(stock_a=0.0, allergen_a=True))
    assert lines[0].is_allergen is True

def test_split_shortages_allergen_only_in_allergen_book():
    # A: short + allergen -> allergen book only; B: short, not flagged -> main only
    order_lines = [{"dish_id": 1, "portions": 10}, {"dish_id": 1, "portions": 10}]
    bom = [
        {"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 0.2},
        {"dish_id": 1, "ingredient_id": 2, "qty_per_portion": 1.0},
    ]
    lines = explode_and_merge(order_lines, bom, _ings(allergen_a=True))
    main, allergen = split_shortages(lines)
    assert {l.ingredient_id for l in main} == {2}
    assert {l.ingredient_id for l in allergen} == {1}
    # disjoint and complete
    assert {l.ingredient_id for l in main} & {l.ingredient_id for l in allergen} == set()
    short_ids = {l.ingredient_id for l in lines if l.shortage > 0}
    assert ({l.ingredient_id for l in main} | {l.ingredient_id for l in allergen}) == short_ids

def test_split_allergen_flagged_but_not_short_lands_nowhere():
    order_lines = [{"dish_id": 1, "portions": 1}]
    bom = [{"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 0.1}]
    lines = explode_and_merge(order_lines, bom, _ings(stock_a=5.0, allergen_a=True))
    main, allergen = split_shortages(lines)
    assert main == [] and allergen == []

def test_split_no_flag_allergen_book_empty():
    order_lines = [{"dish_id": 1, "portions": 1}]
    bom = [{"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 5.0}]
    main, allergen = split_shortages(explode_and_merge(order_lines, bom, _ings()))
    assert len(main) == 1 and allergen == []

def test_fingerprint_stable_and_flag_sensitive():
    order_lines = [{"dish_id": 1, "portions": 10}]
    bom = [{"dish_id": 1, "ingredient_id": 1, "qty_per_portion": 0.2}]
    lines1 = explode_and_merge(order_lines, bom, _ings())
    lines2 = explode_and_merge(order_lines, bom, _ings())
    assert compute_fingerprint(1, lines1) == compute_fingerprint(1, lines2)
    flagged = explode_and_merge(order_lines, bom, _ings(allergen_a=True))
    assert compute_fingerprint(1, lines1) != compute_fingerprint(1, flagged)

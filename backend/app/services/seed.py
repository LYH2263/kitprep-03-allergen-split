from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from app.models.models import BomLine, Dish, Ingredient, KitchenOrder, OrderLine


def _align_demo_allergen(db: Session) -> None:
    """Idempotent alignment for volumes seeded before the allergen feature:
    生抽 is the demo allergen and is short (need 1.75 vs stock 1.0)."""
    db.execute(
        update(Ingredient)
        .where(Ingredient.code == "I-SC")
        .values(is_allergen=True, stock_qty=1.0)
    )
    db.commit()


def seed_if_empty(db: Session) -> None:
    _align_demo_allergen(db)
    if (db.scalar(select(func.count()).select_from(Dish)) or 0) > 0:
        return
    dishes = [("D-HS", "红烧肉套餐"), ("D-YC", "鱼香茄子"), ("D-JT", "鸡汤面")]
    dish_ids = {}
    for code, name in dishes:
        d = Dish(code=code, name=name, portion_unit="份")
        db.add(d); db.flush(); dish_ids[code] = d.id
    ings = [
        ("I-PR", "五花肉", "kg", 8.0, False),
        ("I-EG", "茄子", "kg", 3.0, False),
        ("I-CK", "鸡肉", "kg", 5.0, False),
        ("I-RC", "大米", "kg", 20.0, False),
        ("I-ND", "面条", "kg", 4.0, False),
        ("I-SC", "生抽", "L", 1.0, True),
        ("I-OL", "食用油", "L", 1.5, False),
    ]
    ing_ids = {}
    for code, name, unit, stock, is_allergen in ings:
        i = Ingredient(code=code, name=name, unit=unit, stock_qty=stock, is_allergen=is_allergen)
        db.add(i); db.flush(); ing_ids[code] = i.id
    bom = [
        ("D-HS", "I-PR", 0.25), ("D-HS", "I-RC", 0.15), ("D-HS", "I-SC", 0.02), ("D-HS", "I-OL", 0.03),
        ("D-YC", "I-RC", 0.15), ("D-YC", "I-EG", 0.3), ("D-YC", "I-SC", 0.015), ("D-YC", "I-OL", 0.025),
        ("D-JT", "I-CK", 0.12), ("D-JT", "I-ND", 0.2), ("D-JT", "I-SC", 0.01),
    ]
    for dcode, icode, qty in bom:
        db.add(BomLine(dish_id=dish_ids[dcode], ingredient_id=ing_ids[icode], qty_per_portion=qty))
    order = KitchenOrder(code="KO-0901", outlet="城西门店", status="open")
    db.add(order); db.flush()
    for dcode, portions in [("D-HS", 40), ("D-YC", 30), ("D-JT", 50)]:
        db.add(OrderLine(order_id=order.id, dish_id=dish_ids[dcode], portions=portions))
    db.commit()

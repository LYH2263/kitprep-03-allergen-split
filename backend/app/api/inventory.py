from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Ingredient
from app.schemas import IngredientPatch

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _row(r: Ingredient) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "unit": r.unit,
        "stock_qty": r.stock_qty,
        "is_allergen": r.is_allergen,
        "occupied_qty": round(r.occupied_qty or 0.0, 3),
        "available_qty": round((r.stock_qty or 0.0) - (r.occupied_qty or 0.0), 3),
    }


@router.get("")
def list_inventory(db: Session = Depends(get_db)):
    return [
        _row(r)
        for r in db.scalars(select(Ingredient).order_by(Ingredient.id)).all()
    ]


@router.patch("/{ingredient_id}")
def patch_ingredient(
    ingredient_id: int, patch: IngredientPatch, db: Session = Depends(get_db)
):
    """保存原料含敏标记。不影响已冻结的历史备料单，仅对下一次生成生效。"""
    ing = db.get(Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(status_code=404, detail="原料不存在")
    ing.is_allergen = patch.is_allergen
    db.commit()
    db.refresh(ing)
    return _row(ing)

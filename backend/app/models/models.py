from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Dish(Base):
    __tablename__ = "dishes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    portion_unit: Mapped[str] = mapped_column(String(16), default="份")

class Ingredient(Base):
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    stock_qty: Mapped[float] = mapped_column(Float, default=0.0)
    is_allergen: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false(), nullable=False)
    occupied_qty: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)

class BomLine(Base):
    __tablename__ = "bom_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    qty_per_portion: Mapped[float] = mapped_column(Float)

class KitchenOrder(Base):
    __tablename__ = "kitchen_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    outlet: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="open")

class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("kitchen_orders.id"))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    portions: Mapped[int] = mapped_column(Integer)

class PrepRun(Base):
    __tablename__ = "prep_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("kitchen_orders.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

class _ShortageLineMixin:
    """Shared frozen snapshot columns for the two physical shortage books."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("prep_runs.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    ingredient_code: Mapped[str] = mapped_column(String(32))
    ingredient_name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16), default="")
    need_qty: Mapped[float] = mapped_column(Float)
    stock_qty: Mapped[float] = mapped_column(Float)
    occupied_qty: Mapped[float] = mapped_column(Float)
    shortage_qty: Mapped[float] = mapped_column(Float)

class MainShortageLine(_ShortageLineMixin, Base):
    """主缺料贴 — non-allergen shortages only. Physically separate table."""
    __tablename__ = "main_shortage_lines"
    __table_args__ = (
        UniqueConstraint("run_id", "ingredient_id", name="ux_main_shortage_run_ingredient"),
    )

class AllergenShortageLine(_ShortageLineMixin, Base):
    """敏料专册 — allergen shortages only. Physically separate table (never a filtered view)."""
    __tablename__ = "allergen_shortage_lines"
    __table_args__ = (
        UniqueConstraint("run_id", "ingredient_id", name="ux_allergen_shortage_run_ingredient"),
    )

class OccupationLine(Base):
    """Per-run occupation ledger: covers EVERY needed ingredient, not only shortages."""
    __tablename__ = "occupation_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("prep_runs.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    need_qty: Mapped[float] = mapped_column(Float)
    occupied_qty: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("run_id", "ingredient_id", name="ux_occupation_run_ingredient"),
    )

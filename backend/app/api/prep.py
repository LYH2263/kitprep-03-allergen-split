from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import prep_service

router = APIRouter(prefix="/prep", tags=["prep"])


@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    """生成备料单：按含敏标记拆主贴/专册、记占用；幂等（同参数返回同一套两本账）。"""
    try:
        return prep_service.generate_prep_run(db, order_id)
    except prep_service.OrderNotFoundError:
        raise HTTPException(status_code=404, detail="订单不存在")


@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    """只读：返回该订单最新一次生成；从未生成则返回空骨架（不触发生成）。"""
    return prep_service.latest_payload(db, order_id)


@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    """只读：从主贴、专册两张物理表取最新一次生成的缺料。"""
    return prep_service.shortages_payload(db, order_id)

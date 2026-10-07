from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.schema_ensure import ensure_schema
from app.services.prep_service import LedgerSplitError
from app.services.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="KitPrep", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LedgerSplitError)
async def ledger_split_handler(_request: Request, exc: LedgerSplitError):
    # 分册/占用一致性错误 —— 独立于缺料计算，禁止包装成库存不足。
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "LEDGER_SPLIT_VIOLATION",
                "message": f"主贴/专册/占用分账校验失败，已整次回滚（专册、主贴、占用列全部退回）：{exc}",
            }
        },
    )


app.include_router(api_router, prefix="/api")

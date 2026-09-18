"""封签链校验 API 入口。"""
from __future__ import annotations

from fastapi import FastAPI

from .models import ValidateRequest, ValidateResponse
from .validator import validate_events

app = FastAPI(
    title="封签链校验 API",
    description="用于展品运输交接场景的封签链状态机校验服务",
    version="1.0.0",
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


@app.post(
    "/api/v1/seal-chain/validate",
    response_model=ValidateResponse,
    tags=["seal-chain"],
    summary="校验封签链事件序列",
)
def validate(request: ValidateRequest) -> ValidateResponse:
    """按状态机逐事件校验，返回最终保管人、当前封签、逐事件状态与全部违规。"""
    return validate_events(request.events)

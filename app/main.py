"""FastAPI 应用入口。"""
from __future__ import annotations

from fastapi import FastAPI

from . import __version__, chain
from .models import (
    EventIn,
    EventStatusOut,
    ValidateRequest,
    ValidateResponse,
    ViolationOut,
)

app = FastAPI(
    title="封签链校验 API",
    version=__version__,
    description=(
        "展品运输交接封签链校验：客户端提交按时间排列的封装 / 交接 / 开封 / 重封事件，"
        "服务按状态机逐事件校验，返回最终保管人、当前封签、逐事件状态及全部违规位置与原因。"
        "违规事件不改变状态，也不阻止后续事件的校验。"
    ),
)


def _to_domain(event: EventIn) -> chain.Event:
    """把请求模型转换为状态机事件；时间戳无法解析时置 None，由状态机判违规。"""
    try:
        ts = chain.parse_timestamp(event.timestamp)
    except (ValueError, TypeError, OverflowError):
        ts = None
    return chain.Event(
        type=event.type,
        timestamp=ts,
        seal_id=event.seal_id,
        custodian=event.custodian,
    )


@app.get("/", summary="服务信息")
def root() -> dict:
    return {
        "service": "seal-chain-api",
        "version": __version__,
        "docs": "/docs",
        "validate": "/v1/seal-chain/validate",
        "healthz": "/healthz",
    }


@app.get("/healthz", summary="健康检查")
def healthz() -> dict:
    return {"status": "ok"}


@app.post(
    "/v1/seal-chain/validate",
    response_model=ValidateResponse,
    summary="校验封签链事件序列",
)
def validate_chain(payload: ValidateRequest) -> ValidateResponse:
    result = chain.evaluate(_to_domain(e) for e in payload.events)

    events = [
        EventStatusOut(index=r.index, type=r.type, status=r.status, reason=r.reason)
        for r in result.events
    ]
    violations = [
        ViolationOut(index=r.index, type=r.type, reason=r.reason or "")
        for r in result.violations
    ]
    return ValidateResponse(
        final_state=result.final_state.value,
        final_custodian=result.final_custodian,
        current_seal=result.current_seal,
        total_events=len(events),
        valid_events=len(events) - len(violations),
        events=events,
        violations=violations,
    )

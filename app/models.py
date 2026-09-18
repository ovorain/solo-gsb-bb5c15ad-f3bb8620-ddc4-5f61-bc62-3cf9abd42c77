"""请求 / 响应模型。

设计原则：业务违规（状态机不通过、封签复用、时间倒退等）不会返回 422，
而是在响应中逐事件标记；只有请求体结构本身不合法（如 events 不是数组）
才会返回 422。
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EventIn(BaseModel):
    """单条封签链事件。"""

    type: Optional[str] = Field(
        default=None,
        description="事件类型：seal（封装）/ handover（交接）/ unseal（开封）/ reseal（重封）",
    )
    timestamp: Any = Field(
        default=None,
        description="事件时间：ISO 8601 字符串（可带 Z 或时区偏移）或 Unix 秒时间戳",
    )
    seal_id: Optional[str] = Field(
        default=None, description="封签编号（seal / reseal 必填，全局唯一）"
    )
    custodian: Optional[str] = Field(
        default=None, description="保管人（seal 必填；handover 为接收保管人，必填）"
    )
    note: Optional[str] = Field(default=None, description="备注（可选，不参与校验）")


class ValidateRequest(BaseModel):
    """校验请求：按时间排列的事件列表。"""

    events: list[EventIn] = Field(default_factory=list, description="事件列表")


class EventStatusOut(BaseModel):
    """逐事件校验状态。"""

    index: int = Field(description="事件在请求数组中的位置（从 0 开始）")
    type: Optional[str] = Field(description="事件类型（原样回显）")
    status: Literal["ok", "violation"] = Field(description="ok=有效，violation=违规")
    reason: Optional[str] = Field(default=None, description="违规原因（status 为 violation 时给出）")


class ViolationOut(BaseModel):
    """一条违规记录。"""

    index: int = Field(description="违规事件位置（从 0 开始）")
    type: Optional[str] = Field(description="事件类型（原样回显）")
    reason: str = Field(description="违规原因")


class ValidateResponse(BaseModel):
    """校验响应。"""

    final_state: Literal["sealed", "unsealed"] = Field(description="最终状态")
    final_custodian: Optional[str] = Field(description="最终保管人（无则为 null）")
    current_seal: Optional[str] = Field(description="当前封签编号（未封装时为 null）")
    total_events: int = Field(description="事件总数")
    valid_events: int = Field(description="有效事件数")
    events: list[EventStatusOut] = Field(description="逐事件状态")
    violations: list[ViolationOut] = Field(description="全部违规事件的位置与原因")

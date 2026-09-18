"""请求 / 响应数据模型。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """封签链支持的四种事件类型。"""

    SEAL = "seal"          # 封装：首次（或开封后）以封签封装展品
    HANDOVER = "handover"  # 交接：保管人变更
    UNSEAL = "unseal"      # 开封：拆除当前封签
    RESEAL = "reseal"      # 重封：开封后使用新封签重新封装


class Event(BaseModel):
    """单个封签链事件。timestamp 使用 ISO 8601 格式。"""

    type: EventType
    timestamp: datetime
    seal_id: Optional[str] = Field(default=None, description="封签编号，seal/reseal 事件必填")
    custodian: Optional[str] = Field(default=None, description="保管人，seal/reseal/handover 事件必填")


class ValidateRequest(BaseModel):
    """校验请求：按时间排列的事件列表。"""

    events: List[Event] = Field(default_factory=list)


class EventResult(BaseModel):
    """逐事件判定结果。"""

    index: int
    type: EventType
    status: str = Field(description="ok 或 violation")
    reason: Optional[str] = Field(default=None, description="违规原因，status 为 violation 时给出")


class Violation(BaseModel):
    """违规事件的位置与原因。"""

    index: int
    reason: str


class ValidateResponse(BaseModel):
    """校验响应。"""

    valid: bool = Field(description="整条链是否无任何违规")
    sealed: bool = Field(description="处理完所有有效事件后是否处于封装状态")
    final_custodian: Optional[str] = Field(description="最终保管人")
    current_seal: Optional[str] = Field(description="当前有效封签编号，未封装时为 null")
    events: List[EventResult] = Field(description="逐事件状态")
    violations: List[Violation] = Field(description="所有违规事件的位置与原因")

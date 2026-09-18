"""封签链状态机核心逻辑。

仅依赖 Python 标准库，可脱离 Web 框架独立测试与复用。

状态机规则：
1. 初始状态为「未封装」（unsealed），无保管人、无当前封签。
2. 未封装不得交接（handover）、不得开封（unseal）。
3. 封装（seal）/ 重封（reseal）仅在未封装状态下有效；
   封签编号全局唯一，已使用过的封签（含当前在用的）不得复用，
   即开封后必须换用新封签重封。
4. 交接仅在封装状态下有效，保管人变更为事件中的接收人。
5. 时间戳必须严格递增：与上一个「有效」事件比较；
   违规事件不推进时钟，也不改变任何状态，后续事件继续照常校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SEAL = "seal"          # 封装
HANDOVER = "handover"  # 交接
UNSEAL = "unseal"      # 开封
RESEAL = "reseal"      # 重封

KNOWN_TYPES = (SEAL, HANDOVER, UNSEAL, RESEAL)

STATUS_OK = "ok"
STATUS_VIOLATION = "violation"


class ChainState(str, Enum):
    """封签链状态。"""

    SEALED = "sealed"      # 已封装
    UNSEALED = "unsealed"  # 未封装


# ---------------------------------------------------------------------------
# 时间戳解析
# ---------------------------------------------------------------------------

def parse_timestamp(value: Any) -> datetime:
    """将输入统一解析为带时区的 UTC datetime。

    支持：datetime 对象、ISO 8601 字符串（含 Z 后缀）、Unix 秒时间戳
    （int/float 或纯数字字符串）。无时区的输入按 UTC 处理。
    解析失败抛出 ValueError / TypeError / OverflowError。
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, bool):  # bool 是 int 子类，需先行排除
        raise TypeError("布尔值不是合法时间戳")
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("时间戳为空字符串")
        try:
            if text.endswith(("Z", "z")):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
        except ValueError:
            # 纯数字字符串按 Unix 秒处理；非数字则在此抛出 ValueError
            dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
    else:
        raise TypeError(f"不支持的时间戳类型: {type(value).__name__}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """一条封签链事件。timestamp 为 None 表示缺失或无法解析。"""

    type: Optional[str]
    timestamp: Optional[datetime]
    seal_id: Optional[str] = None
    custodian: Optional[str] = None


@dataclass
class EventResult:
    """单事件校验结果。"""

    index: int
    type: Optional[str]
    status: str  # STATUS_OK / STATUS_VIOLATION
    reason: Optional[str] = None


@dataclass
class ChainResult:
    """整条链的校验结果。"""

    final_state: ChainState
    final_custodian: Optional[str]
    current_seal: Optional[str]
    events: list[EventResult]

    @property
    def violations(self) -> list[EventResult]:
        return [e for e in self.events if e.status == STATUS_VIOLATION]


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------

@dataclass
class SealChain:
    """封签链状态机。违规事件不改变任何字段。"""

    state: ChainState = ChainState.UNSEALED
    custodian: Optional[str] = None
    current_seal: Optional[str] = None
    used_seals: set[str] = field(default_factory=set)
    last_timestamp: Optional[datetime] = None  # 上一「有效」事件时间

    def apply(self, index: int, event: Event) -> EventResult:
        """校验并（在合法时）应用一条事件。"""
        reason = self._check(event)
        if reason is not None:
            return EventResult(index=index, type=event.type,
                               status=STATUS_VIOLATION, reason=reason)
        self._commit(event)
        return EventResult(index=index, type=event.type, status=STATUS_OK)

    # -- 校验：返回违规原因，合法返回 None --------------------------------

    def _check(self, event: Event) -> Optional[str]:
        if event.type not in KNOWN_TYPES:
            return f"未知事件类型：{event.type!r}"

        if event.timestamp is None:
            return "时间戳缺失或无法解析"
        if self.last_timestamp is not None and event.timestamp <= self.last_timestamp:
            return "时间戳必须严格递增（须晚于上一有效事件时间）"

        if event.type in (SEAL, RESEAL):
            if self.state is ChainState.SEALED:
                return "当前处于封装状态，须先开封后才能再次封装"
            if not event.seal_id:
                return "缺少封签编号 seal_id"
            if event.seal_id in self.used_seals:
                return f"封签 {event.seal_id} 已使用，不得复用"
            if event.type == SEAL and not event.custodian:
                return "缺少保管人 custodian"
        elif event.type == HANDOVER:
            if self.state is not ChainState.SEALED:
                return "未封装，不得交接"
            if not event.custodian:
                return "缺少接收保管人 custodian"
        elif event.type == UNSEAL:
            if self.state is not ChainState.SEALED:
                return "未封装，不得开封"
        return None

    # -- 提交：仅在事件合法时调用 ----------------------------------------

    def _commit(self, event: Event) -> None:
        if event.type in (SEAL, RESEAL):
            self.state = ChainState.SEALED
            self.current_seal = event.seal_id
            self.used_seals.add(event.seal_id)  # type: ignore[arg-type]
            if event.type == SEAL:
                self.custodian = event.custodian
        elif event.type == HANDOVER:
            self.custodian = event.custodian
        elif event.type == UNSEAL:
            self.state = ChainState.UNSEALED
            self.current_seal = None  # 封签仍保留在 used_seals 中，不得复用
        self.last_timestamp = event.timestamp


def evaluate(events: Iterable[Event]) -> ChainResult:
    """按顺序校验整条事件链，返回最终状态与逐事件结果。"""
    chain = SealChain()
    results = [chain.apply(i, e) for i, e in enumerate(events)]
    return ChainResult(
        final_state=chain.state,
        final_custodian=chain.custodian,
        current_seal=chain.current_seal,
        events=results,
    )

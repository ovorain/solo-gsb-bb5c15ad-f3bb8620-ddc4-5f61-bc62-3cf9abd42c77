"""状态机核心逻辑测试（仅依赖标准库，可用 unittest 或 pytest 运行）。"""
import unittest
from datetime import datetime, timezone

from app.chain import (
    STATUS_OK,
    STATUS_VIOLATION,
    ChainState,
    Event,
    evaluate,
    parse_timestamp,
)


def ts(text: str) -> datetime:
    return parse_timestamp(text)


def statuses(result):
    return [e.status for e in result.events]


class TestParseTimestamp(unittest.TestCase):
    def test_iso_with_z(self):
        dt = parse_timestamp("2026-09-01T08:00:00Z")
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.hour, 8)

    def test_iso_with_offset_normalized_to_utc(self):
        dt = parse_timestamp("2026-09-01T16:00:00+08:00")
        self.assertEqual(dt, datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc))

    def test_naive_iso_treated_as_utc(self):
        dt = parse_timestamp("2026-09-01T08:00:00")
        self.assertEqual(dt, datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc))

    def test_epoch_number(self):
        dt = parse_timestamp(1788240000)
        self.assertEqual(dt, datetime.fromtimestamp(1788240000, tz=timezone.utc))

    def test_epoch_numeric_string(self):
        self.assertEqual(parse_timestamp("1788240000"), parse_timestamp(1788240000))

    def test_invalid_raises(self):
        for bad in ("not-a-time", "", None, True, [1], {"t": 1}):
            with self.assertRaises((ValueError, TypeError)):
                parse_timestamp(bad)


class TestHappyPath(unittest.TestCase):
    def test_full_journey(self):
        events = [
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("handover", ts("2026-09-01T09:00:00Z"), custodian="李四"),
            Event("handover", ts("2026-09-01T10:00:00Z"), custodian="王五"),
            Event("unseal", ts("2026-09-01T11:00:00Z")),
            Event("reseal", ts("2026-09-01T12:00:00Z"), seal_id="S-002"),
            Event("handover", ts("2026-09-01T13:00:00Z"), custodian="赵六"),
        ]
        result = evaluate(events)
        self.assertEqual(statuses(result), [STATUS_OK] * 6)
        self.assertEqual(result.final_state, ChainState.SEALED)
        self.assertEqual(result.final_custodian, "赵六")
        self.assertEqual(result.current_seal, "S-002")
        self.assertEqual(result.violations, [])

    def test_empty_events(self):
        result = evaluate([])
        self.assertEqual(result.final_state, ChainState.UNSEALED)
        self.assertIsNone(result.final_custodian)
        self.assertIsNone(result.current_seal)
        self.assertEqual(result.events, [])


class TestStateMachineRules(unittest.TestCase):
    def test_handover_requires_sealed(self):
        result = evaluate([
            Event("handover", ts("2026-09-01T08:00:00Z"), custodian="李四"),
        ])
        self.assertEqual(statuses(result), [STATUS_VIOLATION])
        self.assertIn("未封装，不得交接", result.events[0].reason)
        self.assertIsNone(result.final_custodian)

    def test_unseal_requires_sealed(self):
        result = evaluate([
            Event("unseal", ts("2026-09-01T08:00:00Z")),
        ])
        self.assertEqual(statuses(result), [STATUS_VIOLATION])
        self.assertIn("未封装，不得开封", result.events[0].reason)

    def test_double_seal_rejected(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("seal", ts("2026-09-01T09:00:00Z"), seal_id="S-002", custodian="张三"),
        ])
        self.assertEqual(statuses(result), [STATUS_OK, STATUS_VIOLATION])
        self.assertIn("封装状态", result.events[1].reason)
        self.assertEqual(result.current_seal, "S-001")  # 违规事件不改变状态

    def test_seal_reuse_rejected(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("unseal", ts("2026-09-01T09:00:00Z")),
            Event("reseal", ts("2026-09-01T10:00:00Z"), seal_id="S-001"),  # 复用 → 违规
            Event("reseal", ts("2026-09-01T11:00:00Z"), seal_id="S-002"),  # 新封签 → 有效
        ])
        self.assertEqual(
            statuses(result),
            [STATUS_OK, STATUS_OK, STATUS_VIOLATION, STATUS_OK],
        )
        self.assertIn("不得复用", result.events[2].reason)
        self.assertEqual(result.current_seal, "S-002")
        self.assertEqual(result.final_state, ChainState.SEALED)

    def test_current_seal_counts_as_used(self):
        # 已封装状态下封签自然占用；此处验证重封也不能用历史封签
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="A", custodian="张三"),
            Event("unseal", ts("2026-09-01T09:00:00Z")),
            Event("reseal", ts("2026-09-01T10:00:00Z"), seal_id="B"),
            Event("unseal", ts("2026-09-01T11:00:00Z")),
            Event("reseal", ts("2026-09-01T12:00:00Z"), seal_id="A"),  # A 已用过
        ])
        self.assertEqual(statuses(result)[-1], STATUS_VIOLATION)
        self.assertEqual(result.current_seal, None)  # 仍处于开封状态

    def test_unseal_clears_current_seal(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("unseal", ts("2026-09-01T09:00:00Z")),
        ])
        self.assertEqual(result.final_state, ChainState.UNSEALED)
        self.assertIsNone(result.current_seal)
        self.assertEqual(result.final_custodian, "张三")  # 开封不改变保管人

    def test_handover_changes_custodian_only(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("handover", ts("2026-09-01T09:00:00Z"), custodian="李四"),
        ])
        self.assertEqual(result.final_custodian, "李四")
        self.assertEqual(result.current_seal, "S-001")


class TestViolationIsolation(unittest.TestCase):
    """违规事件不改变状态，且不阻止后续可判定检查。"""

    def test_violation_does_not_change_state_and_chain_continues(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("unseal", ts("2026-09-01T09:00:00Z")),
            Event("handover", ts("2026-09-01T10:00:00Z"), custodian="李四"),  # 违规
            Event("reseal", ts("2026-09-01T11:00:00Z"), seal_id="S-002"),     # 仍有效
        ])
        self.assertEqual(
            statuses(result),
            [STATUS_OK, STATUS_OK, STATUS_VIOLATION, STATUS_OK],
        )
        self.assertEqual(result.final_custodian, "张三")  # 违规交接未生效
        self.assertEqual(result.current_seal, "S-002")

    def test_unknown_type_isolated(self):
        result = evaluate([
            Event("freeze", ts("2026-09-01T08:00:00Z")),
            Event("seal", ts("2026-09-01T09:00:00Z"), seal_id="S-001", custodian="张三"),
        ])
        self.assertEqual(statuses(result), [STATUS_VIOLATION, STATUS_OK])
        self.assertIn("未知事件类型", result.events[0].reason)
        self.assertEqual(result.final_state, ChainState.SEALED)

    def test_missing_fields(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), custodian="张三"),          # 缺 seal_id
            Event("seal", ts("2026-09-01T09:00:00Z"), seal_id="S-001"),          # 缺 custodian
            Event("seal", ts("2026-09-01T10:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("handover", ts("2026-09-01T11:00:00Z")),                       # 缺 custodian
        ])
        self.assertEqual(
            statuses(result),
            [STATUS_VIOLATION, STATUS_VIOLATION, STATUS_OK, STATUS_VIOLATION],
        )
        self.assertIn("seal_id", result.events[0].reason)
        self.assertIn("custodian", result.events[1].reason)
        self.assertIn("custodian", result.events[3].reason)
        self.assertEqual(result.final_custodian, "张三")

    def test_unparseable_timestamp_isolated(self):
        result = evaluate([
            Event("seal", None, seal_id="S-001", custodian="张三"),
            Event("seal", ts("2026-09-01T09:00:00Z"), seal_id="S-001", custodian="张三"),
        ])
        self.assertEqual(statuses(result), [STATUS_VIOLATION, STATUS_OK])
        self.assertIn("时间戳", result.events[0].reason)


class TestTimestampOrdering(unittest.TestCase):
    def test_equal_timestamp_rejected(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("handover", ts("2026-09-01T08:00:00Z"), custodian="李四"),
        ])
        self.assertEqual(statuses(result), [STATUS_OK, STATUS_VIOLATION])
        self.assertIn("严格递增", result.events[1].reason)
        self.assertEqual(result.final_custodian, "张三")

    def test_regressed_timestamp_rejected(self):
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("handover", ts("2026-09-01T07:00:00Z"), custodian="李四"),
        ])
        self.assertEqual(statuses(result), [STATUS_OK, STATUS_VIOLATION])

    def test_violation_does_not_advance_clock(self):
        # 违规事件不推进时钟：后续事件与上一「有效」事件比较
        result = evaluate([
            Event("seal", ts("2026-09-01T08:00:00Z"), seal_id="S-001", custodian="张三"),
            Event("handover", ts("2026-09-01T07:00:00Z"), custodian="李四"),  # 违规
            Event("handover", ts("2026-09-01T08:30:00Z"), custodian="李四"),  # 晚于 08:00 → 有效
        ])
        self.assertEqual(
            statuses(result), [STATUS_OK, STATUS_VIOLATION, STATUS_OK]
        )
        self.assertEqual(result.final_custodian, "李四")


if __name__ == "__main__":
    unittest.main()

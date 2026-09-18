"""API 集成测试（需要 fastapi/httpx，未安装时自动跳过）。"""
import unittest

try:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
except ImportError:  # pragma: no cover - 本地无依赖时跳过
    client = None


@unittest.skipIf(client is None, "未安装 fastapi/httpx，跳过 API 集成测试")
class TestApi(unittest.TestCase):
    def test_healthz(self):
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_root(self):
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["service"], "seal-chain-api")

    def test_validate_happy_path(self):
        payload = {
            "events": [
                {"type": "seal", "timestamp": "2026-09-01T08:00:00Z",
                 "seal_id": "S-001", "custodian": "张三"},
                {"type": "handover", "timestamp": "2026-09-01T09:00:00Z",
                 "custodian": "李四"},
                {"type": "unseal", "timestamp": "2026-09-01T10:00:00Z"},
                {"type": "reseal", "timestamp": "2026-09-01T11:00:00Z",
                 "seal_id": "S-002"},
            ]
        }
        resp = client.post("/v1/seal-chain/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["final_state"], "sealed")
        self.assertEqual(body["final_custodian"], "李四")
        self.assertEqual(body["current_seal"], "S-002")
        self.assertEqual(body["total_events"], 4)
        self.assertEqual(body["valid_events"], 4)
        self.assertEqual(body["violations"], [])
        self.assertEqual([e["status"] for e in body["events"]], ["ok"] * 4)

    def test_validate_with_violations(self):
        payload = {
            "events": [
                {"type": "handover", "timestamp": "2026-09-01T08:00:00Z",
                 "custodian": "李四"},                                   # 0 未封装交接
                {"type": "seal", "timestamp": "2026-09-01T09:00:00Z",
                 "seal_id": "S-001", "custodian": "张三"},                # 1 ok
                {"type": "unseal", "timestamp": "2026-09-01T10:00:00Z"},  # 2 ok
                {"type": "reseal", "timestamp": "2026-09-01T11:00:00Z",
                 "seal_id": "S-001"},                                     # 3 封签复用
                {"type": "reseal", "timestamp": "2026-09-01T10:30:00Z",
                 "seal_id": "S-002"},                                     # 4 时间倒退
                {"type": "reseal", "timestamp": "2026-09-01T12:00:00Z",
                 "seal_id": "S-002"},                                     # 5 ok
            ]
        }
        resp = client.post("/v1/seal-chain/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            [e["status"] for e in body["events"]],
            ["violation", "ok", "ok", "violation", "violation", "ok"],
        )
        self.assertEqual([v["index"] for v in body["violations"]], [0, 3, 4])
        self.assertIn("未封装，不得交接", body["violations"][0]["reason"])
        self.assertIn("不得复用", body["violations"][1]["reason"])
        self.assertIn("严格递增", body["violations"][2]["reason"])
        # 违规事件不改变状态：保管人仍是张三，最终由 S-002 重封
        self.assertEqual(body["final_custodian"], "张三")
        self.assertEqual(body["current_seal"], "S-002")
        self.assertEqual(body["final_state"], "sealed")

    def test_validate_empty_events(self):
        resp = client.post("/v1/seal-chain/validate", json={"events": []})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["final_state"], "unsealed")
        self.assertIsNone(body["final_custodian"])
        self.assertIsNone(body["current_seal"])

    def test_epoch_timestamp_accepted(self):
        payload = {
            "events": [
                {"type": "seal", "timestamp": 1788240000,
                 "seal_id": "S-001", "custodian": "张三"},
                {"type": "handover", "timestamp": 1788243600,
                 "custodian": "李四"},
            ]
        }
        resp = client.post("/v1/seal-chain/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["valid_events"], 2)

    def test_malformed_body_returns_422(self):
        resp = client.post("/v1/seal-chain/validate", json={"events": "oops"})
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()

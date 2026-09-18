# 封签链校验 API（Seal Chain Validation）

用于展品运输交接场景的封签链校验服务。客户端提交按时间排列的 **封装 / 交接 / 开封 / 重封** 事件序列，服务按状态机逐事件校验，返回最终保管人、当前封签、逐事件状态及全部违规事件的位置与原因。

## 校验规则（状态机）

| # | 规则 |
|---|------|
| 1 | 未封装状态下不得交接（handover）或开封（unseal） |
| 2 | 已封装状态下不得重复封装 / 重封，须先开封 |
| 3 | 开封后必须使用**新的、未使用过的**封签重封（reseal） |
| 4 | 已使用过的封签不得复用 |
| 5 | 事件时间戳必须严格递增 |

**违规事件不改变状态，也不阻止后续事件的判定**（时间递增性始终与最近一个*有效*事件比较）。

## 快速启动

单条命令（依赖随镜像构建完成，启动即就绪）：

```bash
docker compose up --build
```

- API 地址：`http://localhost:8000`
- 交互式文档（Swagger UI）：`http://localhost:8000/docs`
- 健康检查：`GET http://localhost:8000/health`

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HOST_PORT` | `8000` | 宿主机映射端口，如 `HOST_PORT=9000 docker compose up --build` |

容器内服务固定监听 `0.0.0.0:8000`。

## API 说明

### `POST /api/v1/seal-chain/validate`

**请求体**

```json
{
  "events": [
    {"type": "seal",     "timestamp": "2026-09-18T10:00:00Z", "seal_id": "S001", "custodian": "Alice"},
    {"type": "handover", "timestamp": "2026-09-18T11:00:00Z", "custodian": "Bob"},
    {"type": "unseal",   "timestamp": "2026-09-18T12:00:00Z"},
    {"type": "reseal",   "timestamp": "2026-09-18T13:00:00Z", "seal_id": "S002", "custodian": "Bob"}
  ]
}
```

- `type`：`seal`（封装）/ `handover`（交接）/ `unseal`（开封）/ `reseal`（重封）
- `timestamp`：ISO 8601 时间，需严格递增
- `seal_id`：`seal` / `reseal` 必填，且不得与历史封签重复
- `custodian`：`seal` / `reseal` / `handover` 必填（交接时为接收方）

**响应示例**（上例中若在第 2、3 步之间插入一次未封装状态下的交接）：

```json
{
  "valid": false,
  "sealed": true,
  "final_custodian": "Bob",
  "current_seal": "S002",
  "events": [
    {"index": 0, "type": "seal", "status": "ok", "reason": null},
    {"index": 1, "type": "handover", "status": "violation", "reason": "未封装状态下不得交接"}
  ],
  "violations": [
    {"index": 1, "reason": "未封装状态下不得交接"}
  ]
}
```

| 字段 | 说明 |
|------|------|
| `valid` | 整条链是否无违规 |
| `sealed` | 处理完所有有效事件后是否处于封装状态 |
| `final_custodian` | 最终保管人 |
| `current_seal` | 当前有效封签，未封装时为 `null` |
| `events[]` | 逐事件状态（`ok` / `violation` + 原因） |
| `violations[]` | 所有违规事件的位置（`index`，从 0 开始）与原因 |

> 事件结构不合法（如未知 `type`、缺少 `timestamp`）返回 `422`；语义违规（状态机层面）则在响应的 `violations` 中逐条列出。

### 示例调用

```bash
curl -s http://localhost:8000/api/v1/seal-chain/validate \
  -H 'Content-Type: application/json' \
  -d '{"events": [
        {"type": "seal", "timestamp": "2026-09-18T10:00:00Z", "seal_id": "S001", "custodian": "Alice"},
        {"type": "handover", "timestamp": "2026-09-18T11:00:00Z", "custodian": "Bob"}
      ]}'
```

## 本地开发与测试

```bash
pip install -r requirements-dev.txt
pytest -v
uvicorn app.main:app --reload --port 8000
```

## 项目结构

```
app/
  main.py        # FastAPI 入口与路由
  models.py      # 请求 / 响应模型
  validator.py   # 状态机校验核心
tests/
  test_validator.py
Dockerfile
docker-compose.yml
requirements.txt
```

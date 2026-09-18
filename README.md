# 封签链校验 API（seal-chain-api）

用于展品运输交接的封签链校验服务。客户端提交按时间排列的 **封装 / 交接 / 开封 / 重封**
事件序列，服务按状态机逐事件校验，返回 **最终保管人、当前封签、逐事件状态，以及全部
违规事件的位置与原因**。违规事件不改变状态，也不阻止后续事件的校验。

技术栈：Python 3.12 + FastAPI + Uvicorn，Docker 交付。

## 快速启动（单条命令）

```bash
docker compose up --build
```

依赖随镜像构建自动安装，无需任何手动步骤。启动后：

| 地址 | 说明 |
| --- | --- |
| `http://localhost:8000` | 服务信息 |
| `http://localhost:8000/docs` | Swagger 交互式文档（可在线试调） |
| `http://localhost:8000/healthz` | 健康检查 |
| `POST http://localhost:8000/v1/seal-chain/validate` | 封签链校验接口 |

停止服务：`docker compose down`

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 宿主机映射端口。例：`PORT=9000 docker compose up --build` 后访问 `http://localhost:9000` |

服务本身无其他必需配置，不依赖外部数据库或网络服务。

## API 说明

### `POST /v1/seal-chain/validate`

**请求体**

```json
{
  "events": [
    {"type": "seal",     "timestamp": "2026-09-01T08:00:00Z", "seal_id": "S-001", "custodian": "张三"},
    {"type": "handover", "timestamp": "2026-09-01T09:00:00Z", "custodian": "李四"},
    {"type": "unseal",   "timestamp": "2026-09-01T10:00:00Z"},
    {"type": "reseal",   "timestamp": "2026-09-01T11:00:00Z", "seal_id": "S-002"}
  ]
}
```

**事件字段**

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 是 | `seal`（封装）/ `handover`（交接）/ `unseal`（开封）/ `reseal`（重封） |
| `timestamp` | 是 | ISO 8601 字符串（支持 `Z` 或时区偏移）或 Unix 秒时间戳；无时区按 UTC 处理 |
| `seal_id` | `seal` / `reseal` 必填 | 封签编号，全局唯一 |
| `custodian` | `seal` / `handover` 必填 | `seal` 为封装人，`handover` 为接收保管人 |
| `note` | 否 | 备注，不参与校验 |

**校验规则（状态机）**

1. 初始状态为「未封装」，无保管人、无当前封签。
2. 未封装不得交接、不得开封。
3. 封装 / 重封仅在未封装状态下有效；已使用过的封签（含当前在用的）不得复用，
   即开封后必须换用新封签重封。
4. 交接仅在封装状态下有效，保管人变更为事件中的接收人；开封 / 重封不变更保管人。
5. 时间戳必须严格递增：与上一个 **有效** 事件比较（违规事件不推进时钟）。
6. 违规事件不改变任何状态，后续事件继续照常校验。

**响应字段**

| 字段 | 说明 |
| --- | --- |
| `final_state` | 最终状态：`sealed` / `unsealed` |
| `final_custodian` | 最终保管人（无则为 `null`） |
| `current_seal` | 当前封签编号（未封装时为 `null`） |
| `total_events` / `valid_events` | 事件总数 / 有效事件数 |
| `events[]` | 逐事件状态：`index`（从 0 开始）、`type`、`status`（`ok` / `violation`）、`reason` |
| `violations[]` | 全部违规事件的位置与原因 |

**示例**

```bash
curl -s -X POST http://localhost:8000/v1/seal-chain/validate \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {"type": "seal",     "timestamp": "2026-09-01T08:00:00Z", "seal_id": "S-001", "custodian": "张三"},
      {"type": "handover", "timestamp": "2026-09-01T09:00:00Z", "custodian": "李四"},
      {"type": "unseal",   "timestamp": "2026-09-01T10:00:00Z"},
      {"type": "reseal",   "timestamp": "2026-09-01T11:00:00Z", "seal_id": "S-001"},
      {"type": "reseal",   "timestamp": "2026-09-01T12:00:00Z", "seal_id": "S-002"}
    ]
  }'
```

响应（第 4 个事件复用了已使用的封签 `S-001`，判违规且不改变状态，第 5 个事件仍正常校验）：

```json
{
  "final_state": "sealed",
  "final_custodian": "李四",
  "current_seal": "S-002",
  "total_events": 5,
  "valid_events": 4,
  "events": [
    {"index": 0, "type": "seal",     "status": "ok",         "reason": null},
    {"index": 1, "type": "handover", "status": "ok",         "reason": null},
    {"index": 2, "type": "unseal",   "status": "ok",         "reason": null},
    {"index": 3, "type": "reseal",   "status": "violation",  "reason": "封签 S-001 已使用，不得复用"},
    {"index": 4, "type": "reseal",   "status": "ok",         "reason": null}
  ],
  "violations": [
    {"index": 3, "type": "reseal", "reason": "封签 S-001 已使用，不得复用"}
  ]
}
```

> 说明：业务违规一律返回 `200` 并在响应中逐事件标记；只有请求体结构本身不合法
> （如 `events` 不是数组）才返回 `422`。

## 本地开发

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

运行测试：

```bash
pytest                                   # 全部测试（含 API 集成测试）
python3 -m unittest discover -s tests -t .   # 无 pytest 时可用标准库运行
```

## 项目结构

```
├── app/
│   ├── main.py        # FastAPI 路由与应用入口
│   ├── models.py      # 请求 / 响应模型（Pydantic）
│   └── chain.py       # 封签链状态机核心逻辑（纯标准库，可独立测试）
├── tests/             # 状态机单测 + API 集成测试
├── Dockerfile         # 镜像构建（依赖随构建安装）
├── docker-compose.yml # 单服务编排，单条命令启动
├── requirements.txt       # 运行时依赖
└── requirements-dev.txt   # 开发 / 测试依赖
```

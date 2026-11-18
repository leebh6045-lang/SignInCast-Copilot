# 部署指南

> 目标：让一个陌生环境在 10 分钟内把服务跑起来；同时说明内网/离线部署与安全边界。

## 1. 方式一：本地 Python（开发与演示）

```bash
cd SignInCast-Copilot
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env        # 填 SignInCast 账号 / 模型 Key（可选）
.venv/bin/python -m app.cli # 离线演示（mock 数据 + fake 模型）
make api                    # Web UI: http://127.0.0.1:8000/
```

要求：Python ≥ 3.11（推荐 3.12/3.14）。

## 2. 方式二：Docker（推荐交付）

```bash
cp .env.example .env        # 至少确认 COPILOT_LLM_PROVIDER / Key
docker compose build
docker compose up -d
curl -s localhost:8000/health
# 打开 http://127.0.0.1:8000/
```

说明：
- 容器只监听 `127.0.0.1:8000`，不对外暴露
- `./data` 挂载进容器：fixtures / SQLite / 报告 / trace 都在宿主机可见
- 非 root 用户运行（uid 10001）
- 内置 `HEALTHCHECK`，`docker compose ps` 可看健康状态
- 已在本机验证：Docker Desktop aarch64 + Compose v5.7，镜像约 238MB，健康检查/UI/容器内 CLI/真实模型调用均通过（2026-11-18）；其他环境首次部署仍建议先 `docker compose build` 验证

### 可选：本地模型（Ollama）

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen3:8b   # 模型名以实际可用为准
# .env 改为：
# COPILOT_LLM_PROVIDER=openai_compat
# COPILOT_LLM_BASE_URL=http://ollama:11434/v1
# COPILOT_LLM_API_KEY=ollama
# COPILOT_LLM_MODEL=qwen3:8b
docker compose restart copilot
```

> 本地小模型的工具调用稳定性弱于云端模型；上线前用 `make model-eval` 对比一次。

## 3. 内网 / 无外网部署

1. **镜像迁移**：在有网机器 `docker compose build` → `docker save signincast-copilot:local -o copilot.tar` → 内网 `docker load -i copilot.tar` → 用同一 compose 启动（`--no-build` 或直接 `up`）。
2. **依赖安装（不用 Docker 时）**：有网机器 `pip download -d wheels -e .`，内网 `pip install --no-index --find-links wheels -e .`。
3. **模型**：内网用 Ollama 本地模型，或把 OpenAI 兼容网关部署在内网；没有模型时用 `COPILOT_LLM_PROVIDER=fake` + mock 数据演示（功能验证用）。
4. **业务系统**：`COPILOT_SIGNINCAST_BASE_URL` 指向内网 SignInCast；若无法联通，用 `mock` 模式跑回放。
5. **数据脱敏**：录制真实响应后必须执行 `python scripts/desensitize_fixtures.py` 再打包。

## 4. 配置项（.env）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `COPILOT_LLM_PROVIDER` | `fake` | `fake`（离线规则模型）/ `openai_compat`（真实模型） |
| `COPILOT_LLM_BASE_URL` | DeepSeek | 任意 OpenAI 兼容地址，或 Ollama `http://localhost:11434/v1` |
| `COPILOT_LLM_API_KEY` | 空 | 真实模型密钥；只放本机 `.env` |
| `COPILOT_LLM_MODEL` | `deepseek-chat` | 模型名 |
| `COPILOT_SIGNINCAST_MODE` | `mock` | `mock` 回放 / `record` 录制 / `live` 直连 |
| `COPILOT_SIGNINCAST_USERNAME/PASSWORD` | 空 | SignInCast 教师账号（`live/record` 必需） |
| `COPILOT_SIGNINCAST_FIXTURES_DIR` | `data/fixtures/http` | 回放数据目录 |
| `COPILOT_DB_PATH` | `data/copilot.db` | 动作/审计/会话 SQLite |
| `COPILOT_TRACE_DIR` | `traces` | JSONL trace |
| `COPILOT_REPORT_DIR` | `data/reports` | 导出的 Markdown/Excel |
| `COPILOT_MAX_STEPS` / `RUN_TIMEOUT_S` / token 预算 | 见文件 | 预算硬约束 |

## 5. 数据与备份

| 路径 | 内容 | 是否入库 |
| --- | --- | --- |
| `data/fixtures/http/` | 真实录制响应（已脱敏） | ✅ |
| `data/fixtures/http-sample/` | 合成样例（测试用） | ✅ |
| `data/copilot.db` | 待确认动作 / 审计 / 会话 | ❌ gitignore |
| `data/reports/` | 导出的报告 | ❌ gitignore |
| `traces/` | 运行轨迹 | ❌ gitignore |

备份：`cp data/copilot.db data/copilot-$(date +%F).db`；恢复：先停服务再覆盖。重置：`make reset-db`（清空动作/会话，不影响 fixtures）。

## 6. 安全边界（务必阅读）

1. **接口无鉴权**：`/api/run`、`/api/actions/*` 没有登录态，只适合本机/受信内网；不要绑定 `0.0.0.0` 暴露公网。
2. **确认令牌**：`GET /api/actions/{id}` 会返回 `confirm_token`，当前按"本地人工通道"设计；多用户部署前必须加鉴权。
3. **写操作**：默认 `mock` 模式会拒绝写；`live` 写操作请先在测试课堂/任务上验证，不要对真实班级批量补签。
4. **密钥**：`.env` 已 gitignore；不要贴进日志、Issue、提交记录。
5. **数据脱敏**：录制数据含真实姓名/学号，提交前跑脱敏脚本。

## 7. 故障排查

| 现象 | 排查 |
| --- | --- |
| `CONFIG_ERROR: SignInCast 凭据未配置` | `live/record` 需要教师账号；或改回 `mock` |
| `CONFIG_ERROR: COPILOT_LLM_API_KEY 未配置` | 配 Key 或把 provider 设为 `fake` |
| `没有录制响应：GET /api/...` | 当前路径没录制；先 `make record` 或用 `--sample-fixtures` |
| `UNVERIFIED_NUMBER` | 模型回答含无法溯源数字，被校验拒绝；重试或换模型 |
| 端口占用 | 改 `docker-compose.yml` 或 `uvicorn --port 8001` |
| 容器健康检查失败 | `docker compose logs copilot`；确认 data 目录权限 |

## 8. 升级与回滚

1. 升级前备份 `data/copilot.db`。
2. SQLite 采用版本化迁移（`schema_migrations`），升级自动迁移，**不要手改表结构**。
3. 回滚：切回上一个镜像 tag，并用备份 DB 覆盖。

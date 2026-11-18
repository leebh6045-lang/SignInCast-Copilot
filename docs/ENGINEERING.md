# 工程准则

> 三条总要求：**健壮性、可读性、可维护性**。
> 本文件是硬约束，不是建议。代码评审不通过时，按本文件对应条款反驳或修改。

---

## 0. 总则

1. **先正确，再优雅，最后才是快**。任何"为了赶进度先这样"的决定必须写进 ADR 或 limitations。
2. **每个失败都要可诊断**：错误码 + trace + 足够上下文，禁止静默吞错。
3. **能用代码保证的，不靠模型自觉**：取数、聚合、校验、权限一律用代码。

## 1. 健壮性（Robustness）

| # | 规则 | 现状示例 |
| --- | --- | --- |
| 1.1 | 一切外部调用（模型、HTTP、文件、DB）必须有超时 | `ToolSpec.timeout_s`、`llm_timeout_s` |
| 1.2 | 重试只对**幂等**操作；写操作禁止自动重试 | `read_only=False` 时 attempts=1 |
| 1.3 | 错误必须分类，禁止裸 `except Exception: pass` | `ErrorCode` 15 类；边界统一转换 |
| 1.4 | 边界处才允许宽泛捕获，且必须记录并转换 | `registry._run`、`loop.run` 两处 |
| 1.5 | 外部输入用 pydantic 校验，未知字段拒绝 | `ToolArgs.model_config = {"extra": "forbid"}` |
| 1.6 | 预算硬约束：步数、上下文、token、时间 | `max_steps` / `context_token_budget` / `run_token_budget` / `run_timeout_s` |
| 1.7 | 循环必须能终止：无进展检测 + 步数上限 | 相同工具+参数重复 2 次告警、3 次终止 |
| 1.8 | 写操作必须 HITL + 幂等键 + 审计 | `PendingActionStore` |
| 1.9 | 密钥只走 `SecretStr`/环境变量，绝不进日志与 trace | trace 自动脱敏 + `SecretStr` |
| 1.10 | 关键路径必须留 trace，能复现"为什么这么答" | 每步 decision / tool_result |
| 1.11 | 降级要有明确策略，并告知用户 | M1：工具失败 → 明确说明，不假装成功 |
| 1.12 | 任何数字必须来自工具结果 | 系统提示 + （M2）Verifier 校验 |

## 2. 可读性（Readability）

| # | 规则 |
| --- | --- |
| 2.1 | **依赖方向单向**：`container` → `runtime/guard/tools` → `llm/obs/rag/memory` → `roles/errors/config`。禁止反向依赖 |
| 2.2 | 函数 ≤ 40 行，类单一职责；超了就拆 |
| 2.3 | 命名用领域词：`decision`、`tool_call`、`trace`、`hitl`、`checkpoint`；不用无意义缩写 |
| 2.4 | 公共接口写 docstring；注释解释 **why**，不解释 **what** |
| 2.5 | 配置只有一处：`app/config.py`；其他模块不得直接读 `os.environ` |
| 2.6 | 魔法数字/提示词/价格等常量集中定义并命名 |
| 2.7 | 标识符英文、文档中文；同文件语言一致 |
| 2.8 | 入口只做编排：CLI/API 都复用 `container`，不复制业务逻辑 |
| 2.9 | 输出确定性：排序稳定（工具按名排序）、时间统一 UTC + 毫秒 |
| 2.10 | 禁止隐式全局状态；仅保留 `get_settings` / `get_container` 两个显式缓存 |

## 3. 可维护性（Maintainability）

| # | 规则 |
| --- | --- |
| 3.1 | 可变实现通过 `Protocol` 隔离：`ChatModel` / `Retriever` / `SessionStore` / `StateStore` |
| 3.2 | 依赖注入：工具用工厂函数（`make_*`），由 `container` 装配 |
| 3.3 | 配置外置（`.env`），新增配置必须同时更新 `.env.example` |
| 3.4 | 依赖用版本区间，升级前跑全量测试 |
| 3.5 | 测试分层：单元（纯逻辑）/ 集成（loop + API）/ 回放（eval）；**测试不依赖网络** |
| 3.6 | 外部 IO 才允许替身（FakeChatModel、fixture HTTP）；**禁止伪造成功** |
| 3.7 | 评测即回归：每次改动跑 `eval.run_eval`，与 baseline 对比 |
| 3.8 | 重大决策写 ADR（背景 / 决策 / 后果 / 替代方案） |
| 3.9 | 迁移必须版本化（M2 SQLite 迁移脚本 + 版本号） |
| 3.10 | 不留死代码、注释代码；TODO 必须标里程碑：`TODO(M2): …` |
| 3.11 | 每次提交是"一个可解释的目的"，提交前跑 `pytest` + `ruff` |
| 3.12 | 新增失败路径必须同时补测试与 trace 事件 |

## 4. 测试策略

| 层级 | 覆盖对象 | 工具 |
| --- | --- | --- |
| 单元 | 统计、上下文压缩、注册表、HITL、检索、验证器 | pytest，无 IO |
| 集成 | 主循环（fake 模型）、FastAPI 路由、工具注册 | pytest + TestClient |
| 回放 | 业务场景（工具序列、权限、终止） | `eval/run_eval.py` |
| 真实 | 线上系统冒烟（手动，不进 CI） | CLI |

约束：
- LLM 相关测试一律用 `FakeChatModel`，**不得**为通过测试而放宽断言
- mock 只替换网络边界，业务逻辑必须真跑
- M2 起核心模块（runtime/tools/guard）覆盖率目标 ≥ 80%

## 5. 提交规范

```
feat(m1): 接入 SignInCast 登录与 JWT 刷新
fix(runtime): 修正无进展检测的计数边界
test(registry): 补充写操作不重试的用例
docs(adr): 补充 HITL 的替代方案分析
```

要求：
- 一个提交一个目的，测试通过才提交
- 不提交 `.env`、`traces/`、真实学生数据
- 破坏性改动在提交正文里写清影响面与回滚方式

## 6. 自检清单（提交前 10 条）

1. [ ] 新增代码有测试，且测试真的会失败（改坏一处能红）
2. [ ] 所有新外部调用都有超时
3. [ ] 新错误路径有 `ErrorCode` 且写 trace
4. [ ] 没有把模型输出直接当事实（数字/结论有来源）
5. [ ] 写操作仍然只能"提议"，不能执行
6. [ ] 没有新增隐式全局状态
7. [ ] 配置项在 `.env.example` 有说明
8. [ ] 文档/ADR/limitations 同步更新
9. [ ] `ruff check` 与 `pytest` 通过
10. [ ] 读一遍 diff：能否半年后看懂为什么这么写

## 7. 明令禁止

- 裸 `except: pass`、吞掉异常继续执行
- `print()` 调试留在业务代码（CLI 输出除外）
- 把密钥、token、真实学生信息写进代码/日志/trace/测试
- 用 mock 伪造"通过"或伪造指标
- 为了"看起来完整"而写未经验证的功能说明
- 未标里程碑的 TODO

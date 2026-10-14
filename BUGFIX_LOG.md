# BUGFIX LOG

本文件记录已发现和修复的 bug，方便追溯和避免再犯。

---

## BUG-AGENT-2026-07-26-001: Wave Lease Reaper 静默失败导致 Zombie Lease 阻塞

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-26 |
| 修复日期 | 2026-07-26 |
| 严重程度 | P1（阻塞开发流程） |
| 影响范围 | `scripts/dev/stack_supervisor/daemon.py`, `scripts/dev/wave_orchestrator/core.py` |
| 出现次数 | 1（首次发现并一次性彻底修复） |
| 关联 roadmap | Wave Lease Reaper 修复方案（dev-shell 内部 roadmap，未归档进本仓） |

### 现象

1. `./myrm restart` 或 `./myrm ready` 被 `WAVE_STACK_WRITE_DENIED` 阻塞
2. `lease-owners/` 目录积累 28 个过期 owner 文件
3. supervisor 日志显示 "Wave lease reaper failed to execute" **51 次**
4. 需频繁手动清理才能恢复正常开发流程

### 根因

`stack_supervisor/daemon.py` 的 `_reap_wave_leases()` 方法通过 **subprocess → bash → python** 三跳链调用 `wave.sh reap`：

```
daemon.py → subprocess.run(["bash", "wave.sh", "reap"]) → wave.sh → python -m wave_orchestrator.cli reap
```

当 server 的 venv Python 路径不可用（如 venv 重建中）或 subprocess 超时（30s），整个 reap 周期静默失败。加上默认 `DEFAULT_LEASE_TTL_SEC = 3600`（1 小时），zombie lease 存活时间极长。

### 修复

1. **消除三跳链**：`_reap_wave_leases()` 改为直接 Python import `wave_orchestrator.core.reap()`
2. **同步修复 gate 检查**：`_wave_stack_write_allowed()` 改为直接 Python import `check_stack_write_gate()`
3. **缩短 TTL**：`DEFAULT_LEASE_TTL_SEC = 3600 → 900`（15min）；正常 heartbeat 不受影响

### 验证

- 新 supervisor 启动后零 reaper 失败
- `reap()` 直接调用立即清理所有 zombie lease
- `check_stack_write_gate()` 正确返回 gate 状态

### 踩坑经验

1. **永远不要用 subprocess 调用自己能直接 import 的 Python 模块** — 引入不必要的 bash/venv 路径依赖
2. **TTL 应足够短以限制 reaper 失效的影响** — heartbeat 机制保证正常测试不受短 TTL 影响
3. **watchdog 的可靠性必须高于被 watch 的组件** — 如果 watchdog 自身失败率高，它就失去了存在意义
4. **日志里的 WARNING 不能被忽视** — 51 次 "reaper failed" 累积到系统不可用才发现，应有告警
5. **排队等待超时应匹配实际场景** — 单开发机器 4 路并行，单测试 10min 内完成，等待不应超过 5min

---

## BUG-AGENT-2026-07-26-002: E2E 排队等待超时过长导致假性卡死

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-26 |
| 修复日期 | 2026-07-26 |
| 严重程度 | P2（用户体验差，误判为系统 hang） |
| 影响范围 | `scripts/dev/lib/dev_gate_contract.py` |
| 出现次数 | 1（设计问题，首次识别） |
| 关联 | BUG-AGENT-2026-07-26-001（zombie lease + 长等待 = 灾难组合） |

### 现象

测试启动后长时间无输出，用户误判为系统 hang，实际是在排队等待 lease slot。

### 根因

4 个排队等待常量均设为 900s（15 分钟），对单开发机器过长：
- `E2E_MUX_ADMISSION_WAIT_SEC = 900`
- `MUX_UPSTREAM_WAIT_SEC = 900`
- `E2E_UNIFIED_WAIT_SEC = 900`
- `LIVE_AGENT_STREAM_WAIT_SEC = 900`

与 BUG-001 的 zombie lease 叠加时，等待时间从 15min 变为无限等待（zombie 占槽 1h + 排队 15min）。

### 修复

全部缩短为 300s（5 分钟）：
- 4 路 LIVE 并行，单测试 <10min，正常情况下 slot 在 2-3min 内释放
- 300s 足够覆盖所有正常场景，同时快速 fail 异常情况

### 踩坑经验

1. **等待超时 = max(正常等待) × 安全系数**：正常 slot 释放 ~2-3min，安全系数 2x = 5min 合理
2. **zombie lease + 长等待 = 灾难组合**：两个 "安全保守" 的设计叠加产生最差体验

---

## BUG-AGENT-2026-07-26-003: E2E 等待超时分散硬编码导致修改不一致

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-26 |
| 修复日期 | 2026-07-26 |
| 严重程度 | P3（配置漂移、维护成本） |
| 影响范围 | 多个 bash/python 文件硬编码 `:-900` 默认值 |
| 出现次数 | 1（首次系统性发现） |
| 关联 | BUG-AGENT-2026-07-26-002（修改 `dev_gate_contract.py` 后发现不生效） |

### 现象

修改 `dev_gate_contract.py` 中的等待常量为 300s 后，实际运行时仍表现为 900s 等待。

### 根因

多个 bash 脚本和 Python 文件硬编码了 `:-900` 默认值，绕过了 `dev_gate_contract.py` 的 SSOT：

- `scripts/dev/test.sh:378` — `MYRM_E2E_LEASE_WAIT_SEC:-900`
- `scripts/dev/lib/e2e_bootstrap.sh:127,226,527` — 三处 `:-900`
- `scripts/dev/lib/_e2e_gate_wave.py:30` — `_DEFAULT_QUEUE_WAIT_SEC = 900`
- `scripts/dev/chrome_e2e_runtime.py:206` — 硬编码 900
- `scripts/dev/lib/e2e_stream_lock.py:130` — `--wait` 默认 900.0
- `myrm-agent/scripts/dev/lib/e2e_shared_ui_hydrate.py:19` — `DEFAULT_WAIT_SEC = 900`
- `myrm-agent/scripts/dev/lib/e2e_mux_admission.py:24` — `DEFAULT_WAIT_SEC = 900`
- `myrm-agent/scripts/dev/lib/wave-lease-owner.sh:70` — `MYRM_E2E_LEASE_WAIT_SEC:-900`
- `myrm-agent/myrm-agent-server/tests/e2e/desktop_approval/conftest.py:32` — 默认 900
- 3 个测试文件断言 `== 900` 的旧常量值

### 修复

1. `test.sh` 改为从 `dev_gate_contract.E2E_UNIFIED_WAIT_SEC` 动态读取
2. 其他所有硬编码改为 300（与 SSOT 一致）
3. 测试断言更新为 `== 300`

### 踩坑经验

1. **分布式默认值是维护灾难** — 单一 SSOT 必须贯穿所有调用链
2. **改常量后必须全局 grep** — `rg ":-900" "== 900" "default.*900"` 类搜索是必须步骤
3. **bash 脚本中的 `${VAR:-default}` 是隐性 SSOT 违规** — 应通过 Python 一行代码从合约文件读取

---

## BUG-AGENT-2026-07-27-001: Extension Bridge Settings 双 API 前缀 404 + Tab 路由遗漏

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-27 |
| 修复日期 | 2026-07-27 |
| 严重程度 | P1（Settings 扩展页不可用 + 误导性「无法连接服务器」） |
| 影响范围 | `myrm-agent-frontend/src/services/extension.ts`、`app/settings/[tab]/page.tsx`、`SettingsLayout.tsx`、`locales/*/metadata.settingsTabs` |
| 出现次数 | 1 |

### 现象

1. `/settings/extensionBridge` 直接访问 **404**
2. 从菜单进入扩展页时顶部红色横幅 **「无法连接服务器」**，但 `curl /api/v1/extension/status` 返回 200
3. Chrome MCP E2E / 手动 MCP 验证 UI 矩阵不可见

### 根因

1. **双 API 前缀**：`extension.ts` 调用 `apiRequest(getApiUrl('/extension/status'))`；`apiRequest` → `fetchWithTimeout` 内部再次 `getApiUrl()` → 实际请求 **`/api/v1/api/v1/extension/status`（404）**
2. **Tab SSOT 遗漏**：`extensionBridge` / `connect` 等在 `SettingsMenu` + `SECTION_COMPONENTS` 已登记，但 `page.tsx` `VALID_TABS` 与 `SettingsLayout.tsx` `BASE_TABS` 缺失 → App Router `notFound()`
3. **metadata 缺失**：`metadata.settingsTabs.extensionBridge` 未写入 locales → 页面 title 回退异常

### 修复

1. `extension.ts`：REST 改为 `apiRequest<T>('/extension/...')`（与 `kanban.ts` 一致）；移除多余 `.json()`；`getExtensionWebSocketUrl()` loopback dev 回退端口 **8080**（`isLoopbackDevHost()`）
2. `page.tsx` / `SettingsLayout.tsx`：补齐 `extensionBridge`、`connect` 等 Tab
3. `locales/{en,zh,zh-TW,ja}.json`：补齐 `metadata.settingsTabs`

### 验证

- 浏览器 fetch `/api/v1/extension/status` = 200；双前缀路径 = 404（修复前）
- MCP：`fetchError: false`、WS `ws://127.0.0.1:8080/api/v1/ws/extension`、4 行能力矩阵可见
- 单元：`tests/api/extension/test_extension_api.py` **96 passed**
- Chrome E2E：`tests/e2e/test_extension_bridge_chrome_e2e.py`（READ lane）

### 踩坑经验

1. **前端 service 层 REST 路径 SSOT = 相对 `/extension/...`**，禁止先 `getApiUrl()` 再交给 `apiRequest`
2. **Settings Tab 三处登记**（`VALID_TABS` / `BASE_TABS` / `SettingsMenu` + i18n metadata）缺一即 404 或不可达
3. **「无法连接服务器」横幅要先查 Network 实际 URL**，不要假设 backend down
4. **Chrome E2E Settings 断言须 scoped 到 `[data-section][data-active]`** — SettingsLayout 缓存 hidden Tab，`document.body` / 首个 `h2` 会假阳性；CDP 已发现时 UI 显示 `cdpRiskHelp` 而非 `chrome://inspect/#...` 文案

---

## BUG-AGENT-2026-07-27-002: Stream-Retry E2E Fixture 文案触发 Risk Gate（误报 busy 失败）

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-27 |
| 修复日期 | 2026-07-27 |
| 严重程度 | P2（测试假红，非生产逻辑 bug） |
| 影响范围 | `app/api/chats/test_fixtures/stream_retry_busy.py`, Chrome READ E2E |
| 出现次数 | 1 |
| 关联 roadmap | Stream-Retry 幂等闭合修复方案（dev-shell 内部 roadmap，未归档进本仓） |

### 现象

Chrome READ E2E `test_stream_retry_contract_chrome_e2e` 在 busy 断言阶段收到 `risk_blocked`（`contract_quote_keywords`），而非 `AgentBusyError`。

### 根因

Fixture 查询 `_BUSY_QUERY_TEXT` 含英文 **「contract」**，命中 [`risk_gate.py`](myrm-agent/myrm-agent-server/app/services/agent/stream_session/risk_gate.py) / [`constants.py` rule `contract_quote_keywords`](myrm-agent/myrm-agent-server/app/services/risk/constants.py)。Risk 检查在 orchestrator **reserve 之前**，故 retry POST 从未到达 busy 路径。

### 修复

1. `_BUSY_QUERY_TEXT` → `"E2E stream retry busy fixture ping message"`（无 risk 关键词）
2. 新增 `test_busy_fixture_query_is_not_risk_blocked` 回归锁

### 验证

- `./myrm test -m chrome_e2e …/test_stream_retry_contract_chrome_e2e.py` 绿（多轮）

### 踩坑经验

1. **E2E fixture 文案必须对照 risk 规则表** — 含 contract/quote/invoice 等词会假失败
2. **测试失败要区分 risk_blocked vs AgentBusyError** — SSE `type` 不同

---

## BUG-AGENT-2026-07-27-003: 前端未识别 SSE AgentBusyError → 弱网重试不 requeue（跨层契约断裂）

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-27 |
| 修复日期 | 2026-07-27 |
| 严重程度 | **P0（生产行为错误）** |
| 影响范围 | `myrm-agent-frontend/src/store/chat/streamConsumer.ts`, `useMessageInput.ts` requeue 链 |
| 出现次数 | **2**（① 宣称 PERFECT CLOSURE 时未发现；② 深度审计本轮发现） |
| 反复修复 | 同一类问题：测试/mock 与生产响应形态不一致，导致「API 绿 ≠ FE 绿」 |

### 现象

同 `message_id` 活跃重试时，后端正确返回 busy SSE，但用户输入**不会**进入 message queue；UI 仅显示 assistant error step。

### 根因

1. 后端 [`stream_busy.py`](myrm-agent/myrm-agent-server/app/services/agent/stream_session/stream_busy.py)：`StreamingResponse` **HTTP 200** + SSE `{type:error, error_type:AgentBusyError, status_code:409}`
2. 前端 `executeStreamWithRetry` 仅在 **`res.status === 409`** 时 throw `AgentBusyError`
3. SSE busy 进入 `agentControlEvents` 作普通 ERROR 渲染，**不 throw**
4. Vitest 仅 mock HTTP 409，**未覆盖**生产 SSE 路径

### 修复

1. `streamConsumer.ts`：`isAgentBusySseEvent()` — 在 `handleMessageStream` **之前** throw `AgentBusyError`
2. inner catch 对 `AgentBusyError` re-throw
3. Vitest：`HTTP 200 + SSE error_type AgentBusyError` 用例

### 验证

- Vitest streamConsumer 14/14 + resumeApprovalStream 1/1
- Chrome E2E UI `retryStreamWithSameMessageId` → `{busy:true}`

### 踩坑经验

1. **busy 契约 = SSE envelope，不是 HTTP status code** — 文档/测试必须写清
2. **API integration 绿 ≠ 跨层绿** — 必须 trace FE consumeStream 全分支
3. **Vitest mock 必须镜像生产** — mock 409 会掩盖 200+SSE 真实形态
4. **为何反复出现**：多次签收基于 API/Chrome API POST 断言，未审计 FE throw→requeue 链

---

## BUG-AGENT-2026-07-27-004: Multiplex 路径 drain POST body 丢弃 AgentBusyError SSE

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-27 |
| 修复日期 | 2026-07-27 |
| 严重程度 | **P1（生产默认路径）** |
| 影响范围 | `streamConsumer.ts` multiplex 分支 |
| 出现次数 | 1（与 BUG-003 同轮深度审计发现） |
| 关联 | BUG-003（direct SSE 已修，multiplex 仍漏） |

### 现象

生产默认 `shouldUseMultiplexedAgentStream() === true` 时，busy 重试可能被静默丢弃，用户既不 requeue 也不见明确 busy 信号。

### 根因

1. Multiplex **成功**：POST 返回 **JSON accepted**（[`stream_pump.py:145-147`](myrm-agent/myrm-agent-server/app/services/agent/stream_session/stream_pump.py)）
2. Busy **early terminal**：POST 返回 **text/event-stream**（未 launch pump）
3. 旧逻辑：`multiplexBridge` 存在时 **一律** `drainResponseBodyInBackground(res)` + 读 workspace bridge → busy SSE 被 drain 丢弃

### 修复

Multiplex 分支：若 POST `content-type` 含 `text/event-stream` → **直接 `consumeStream(res)`**；仅 JSON/非 SSE 才 drain+bridge。

### 验证

- Vitest：`throws AgentBusyError on multiplex POST when body is direct SSE busy envelope`
- 14/14 streamConsumer passed

### 踩坑经验

1. **Multiplex 有两种 POST 响应形态** — JSON vs SSE；分支必须按 content-type 分流
2. **E2E 设 `__MYRM_E2E_DIRECT_SSE__` 会绕过 multiplex** — UI 测绿不等于 multiplex 生产绿；需 Vitest 补位

---

## BUG-AGENT-2026-07-28-005: HITL resume / plan confirm 未检测 SSE AgentBusyError

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-07-28 |
| 修复日期 | 2026-07-28 |
| 严重程度 | **P2（低频 HITL 双点）** |
| 影响范围 | `resumeApprovalStream.ts`、`chat.ts` `resumePlanConfirmStream` |
| 关联 | BUG-003（同 SSE envelope 形态） |

### 现象

活跃 session 下 HITL resume POST 返回 HTTP 200 + SSE `{error_type:AgentBusyError}` 时，resume 路径仅检查 HTTP 409，busy 被吞掉或仅打 log。

### 修复

1. 导出 `isAgentBusySseEvent` from `streamConsumer.ts`
2. `resumeApprovalStream` / `resumePlanConfirmStream` 在 `handleMessageStream` 前检测并 throw `AgentBusyError`
3. Vitest：`resumeApprovalStream.test.ts`

### 验证

- Vitest resumeApprovalStream 1/1 + streamConsumer 14/14

---

## BUG-AGENT-2026-09-03-001: SharedContext 序列化 bindings 迭代异常导致 API 500

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-09-03 |
| 修复日期 | 2026-09-03 |
| 严重程度 | **P2（API 健壮性与测试阻断）** |
| 影响范围 | `app/api/memory/operations/shared_context/shared_context_serializers.py`, `app/main.py` |
| 出现次数 | 1（集成测试中暴露） |
| 关联 | 共享上下文服务 `test_live_shared_context_memory_smoke.py` |

### 现象

在共享上下文接口调用中，创建或读取 SharedContextModel 时偶发 500 Internal Server Error，错误穿透至最外层通用异常捕获。

### 根因

1. `context_to_item` 函数中通过列表推导式提取 `assigned_agent_ids`：`[b.target_id for b in (context.bindings or []) if getattr(b, "target_type", None) == "agent"]`。当 `bindings` 包含非标对象或在边缘情况下访问属性抛出异常时，无局部异常保护，直接导致整次序列化失败崩溃；
2. `app/main.py` 中数据库与自定义错误处理器的注册顺序排在通用 404/Exception 之后，导致业务自定义异常拦截失效。

### 修复

1. 在 `shared_context_serializers.py` 中增加保护性 `try-except Exception` 兜底，解析失败时优雅降级为返回空列表 `[]`；
2. 调整 `app/main.py` 异常处理器注册顺序，将 `register_database_operational_handlers` 和 `register_exception_handlers` 提升到全局通用异常处理器之前。

### 验证

- `test_shared_context_service.py` 17 项全通过；
- `test_live_shared_context_memory_smoke.py` 冒烟测试全通过。

### 踩坑经验

1. **DTO/Model 序列化函数必须具备绝对容错能力** — 数据对象展示层转换绝不能因为关联数据的非核心子字段异常而直接炸掉主流程接口；
2. **FastAPI 异常处理器注册顺序遵循后注册者优先级规则** — 业务领域异常必须保证优先命中，防止被顶层全局 `Exception` 粗暴拦截掩盖真实根因。

---

## BUG-AGENT-2026-09-03-002: 智能体技能装配隐式 Fallback 认知鸿沟与 WYSIWYG 所见即所得收敛

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-09-03 |
| 修复日期 | 2026-09-03 |
| 严重程度 | **P2（用户心智一致性与认知体验重大缺陷）** |
| 影响范围 | `app/core/skills/effective_skill_ids.py`, `app/services/agent/builtin_specs/builtin_initializer.py`, `myrm-agent-frontend/.../SkillsSectionPanel.tsx`, `AgentConfigCards.tsx`, `locales/` |
| 出现次数 | 1（架构复盘与用户体验审计发现） |
| 关联 | 技能系统与智能体配置契约 |

### 现象

在 WebUI 智能体配置面板中，卡片显示技能「0 未选择」，但后端在实际会话运行时却暗箱将「空技能名单」Fallback 为「加载系统已启用的全部 20+ 个技能」；当用户尝试显式勾选 1 个技能后，其他技能突然消失，与用户预期的「0 个技能就是没有技能」产生严重认知冲突。

### 根因

1. **后端隐式 Fallback 历史技术债**：`effective_skill_ids.py` 的 `resolve_runtime_skill_ids` 存在兜底逻辑：若 `profile_skill_ids` 为空，自动读取用户全局已启用技能作为兜底；
2. **出厂配置缺失显式声明**：内置通用智能体在数据库中初始化时 `skill_ids = []`，依赖了上述隐式 fallback，导致无法在前端向用户诚实展示已装配技能；
3. **前端缺少批量装配操作**：技能配置面板仅支持单卡勾选，缺失「一键全选」与「清空」快捷能力，缺乏数量统计与纯指令模式提示。

### 修复

1. **后端契约收敛**：`resolve_runtime_skill_ids` 彻底纯净化为所见即所得标准，`profile_skill_ids` 为空或 None 时严格返回 `[]`，不再暗箱 Fallback；
2. **初始化显式装配**：`builtin_initializer.py` 在启动初始化时，为默认通用智能体显式写入所有已启用的预置技能（设为 peripheral 按需加载，保护 Prompt Cache）；
3. **前端交互与所见即所得闭环**：
   - `SkillsSectionPanel.tsx` 增加「全选」与「清空」快捷按钮；
   - 增加装配统计徽章（如 `X / Y 已装配`）以及 0 技能装配时的「未装配技能 · 纯指令模式」友好解释条；
   - `AgentConfigCards.tsx` 卡片在 0 技能时明确展示「未装配技能（纯指令模式）」；
4. **全语系 i18n 覆盖**：完成中、英、日、韩、繁中、德 6 种多语言本地化，修复预存的 4 处 Obsidian 引用遗漏，`verify:i18n` 门禁 100% 通过。

### 验证

- `test_effective_skill_ids.py` 3/3 项全部通过（含 WYSIWYG 空名单与 legacy 规范化测试）；
- `test_builtin_initializer.py` 18/18 项全部通过；
- `test_discovery_mount.py` 8/8 项全部通过；
- `test_discovery_install_enable_integration.py` 14/14 项全部通过；
- 前端 `bun run verify:i18n` 100% 通过（1849 个代码文件无缺失键引用）。

### 踩坑经验

1. **禁止在运行时做违背 UI 表象的暗箱隐式兜底** — 用户在界面上看到什么，底层就必须严格执行什么（WYSIWYG）。如果默认通用智能体需要全部能力，应当在初始化数据层显式赋满，而非在底层代码留一个反直觉的空列表 Fallback；
2. **渐进披露与快捷操作缺一不可** — 在提供精准控制能力的同时，必须提供「一键全选」和「清空」等低成本批量操作，配合清晰文案告知用户系统当前的运行模式。

---

## BUG-AGENT-2026-09-03-002: 多模态媒体工具输入大图导致 413、EXIF 角度颠倒与 RGBA 保存 JPEG 崩溃隐患

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-09-03 |
| 修复日期 | 2026-09-03 |
| 严重程度 | **P1（多模态工具链路可用性致命隐患）** |
| 影响范围 | `app/ai_agents/media_tools/`, `app/tasks/executors/video_executor.py`, `app/ai_agents/general_agent/tool_setup.py` |
| 出现次数 | 1（架构复盘与边界审查发现） |
| 关联 | 多模态媒体工具输入防护与图像消毒 |

### 现象

用户上传真实手机摄影大图（如 iPhone 拍的 15MB~25MB 照片，分辨率 4032x3024 带有 EXIF 旋转标签，或带透明通道 RGBA 的设计素材）调用 `image_tool` 或 `video_tool`（如图生视频 I2V）时：
1. 超大图直接 Base64 编码后膨胀超出下游模型网关限制，下游返回 `413 Payload Too Large` 导致 Agent 任务报错中断；
2. EXIF 朝向标签在传递给部分仅接收裸图像帧的视频生成 API 时丢失，导致生成视频人脸和物体横躺或倒置 90 度；
3. 带透明底板的 RGBA/P 图在转换为标准 JPEG 保存或传输时，Pillow 会直接抛出 `OSError: cannot write mode RGBA as JPEG` 导致未捕获 500 异常。

### 根因

1. **媒体工具层缺失自适应消毒纯函数**：`image_agent_tool.py` 与 `video_agent_tool.py` 裸传或裸下载字节，未进行统一的物理像素转置、通道融合与尺寸体积门禁；
2. **模块依赖存在深层穿透**：外部业务（如 `tool_setup.py`）跳过 `media_tools/__init__.py` 门面直接深层导入各个内部子模块，导致包边界模糊；
3. **测试夹具单例污染**：`test_media_filter_e2e.py` 中 `ModelCapabilityLearner` 单例污染导致跨测试状态泄露。

### 修复

1. **落地 `image_clamp.py` 纯函数**：实现 `clamp_image_payload` 图像消毒管线：
   - 自动检测并物理烘焙 EXIF Orientation（`ImageOps.exif_transpose`）；
   - 对 RGBA/LA/P 模式与纯白底板进行 Alpha 混合，平滑合成纯净 RGB；
   - 限制长边最大 2048px 并按 LANCZOS 等比缩放，压缩体积 90% 以上；
   - 小图与合规图无损直通（Lossless Bypass），坏图受控降级容错，显式关闭 Pillow 图像对象防止内存泄漏；
2. **包级出口门面统一收敛**：重构 `app/ai_agents/media_tools/__init__.py` 为标准 Facade，通过 `__all__` 统一暴露核心工厂与门面函数，消除深层引用；
3. **多模态全链路挂载**：在 `image_agent_tool.py`（下载输入）、`video_agent_tool.py`（本地输入）与 `video_executor.py`（执行器解析后）完成端到端防御闭环；
4. **单测夹具与数据库隔离**：修复 `tests/api/agent/conftest.py` 中 `Base.metadata.create_all` 显式预加载模型，并在 `test_media_filter_e2e.py` 中引入 `_clean_capability_learner` autouse fixture 自动清空污染。

### 验证

- `scripts/dev/tests/test_*_static.py` 249/249 全部通过；
- `tests/unit/ai_agents/media_tools/test_image_clamp.py` 与相关任务单测 58/58 全部通过；
- `tests/unit/ai_agents/` 全模块单元测试 66/66 全部通过（通过率 100%）。

### 踩坑经验

1. **多模态工具输入必须在服务层设防** — 模型与下游服务网关对多媒体格式极其敏感，千万不要假设用户传入的图片一定格式纯正、体积小巧；必须在数据进入引擎前进行物理朝向烘焙、透明度混合与自适应降采样；
2. **保持 Harness 纯粹性** — 图像 C 扩展库（如 Pillow）应留在 Server 业务层，Harness 引擎维持纯粹和轻量，防止重型依赖反向污染执行框架。

---

## BUG-AGENT-2026-09-17-001: 前端 `require('./sandbox')` 悬空导入导致全站 500（模块删除误判动态加载）

| 属性 | 值 |
|------|-----|
| 发现日期 | 2026-09-17 |
| 修复日期 | 2026-09-17 |
| 严重程度 | **P0（前端全站不可用：所有路由 HTTP 500）** |
| 影响范围 | `myrm-agent-frontend/src/services/file-service/`、`src/components/features/message-input-actions/AttachButton.tsx`（消费方） |
| 出现次数 | 1（一次性根治 + 新增静态门禁防止复发） |
| 关联 | `scripts/dev/tests/test_*_static.py`、`myrm-agent-frontend/scripts/check_module_resolution.py` |

### 现象

前端所有路由（`/`、`/memory`、`/settings`）返回 **HTTP 500**，页面为 Next 错误页而非应用；`tsc --noEmit` 与 oxlint 均**不报错**，构建期无任何提示。

### 根因

提交 `acd1883c1`（`refactor(frontend): delete 56 modules unreachable from every entrypoint`）以「可达性扫描确认这些模块无人引用」为由删除了 `src/services/file-service/sandbox.ts`。但该模块的真实引用点是**动态 CommonJS require**：

```ts
// src/services/file-service/index.ts:34
const { sandboxFileService } = require('./sandbox');
```

`tsc` 对 `require` 的签名是 `(id: string) => any`，specifier 是运行时字符串，**类型系统无法校验目标是否存在**；可达性扫描器只认静态 `import` 字面量，因此漏判。该模块经 `AttachButton → MessageInput → Chat → ChatWindow → app/page.tsx` 挂载，缺失即导致整个页面树编译失败。删除提交的说明文字恰好写明了这个错误假设：*"A textual scan confirmed every import in the tree is a static string literal, so no dynamic loader can reach them."*

### 修复

1. **恢复被误删模块**：`git show acd1883c1^:...sandbox.ts` 取回并逐字节比对一致（139 行）；
2. **补回 `_ARCH.md` 漂移行**：`services/file-service/_ARCH.md` 文件清单恢复 `sandbox.ts` 行；
3. **新增根因门禁**（由并行开发者落地 `check_module_resolution.py`）：按 bundler 同款「扩展名替换 + index 规则」解析 `from` / `import()` / `require()` / 相对与别名路径，命中磁盘不存在即 CI 失败，专门填补 `require` 盲区；并接入 `frontend-build.yml`。

### 验证

- 恢复后 `curl http://localhost:3000/` 立即由 **HTTP 500 → HTTP 200**，`/memory`、`/settings` 全部 200 且无 500 页；
- `check_module_resolution.py` 全仓 2628 个源文件 **0 未解析**；
- 人工审计被删 56 个文件：逐一检查 `require`/`import()`/`React.lazy`/`next/dynamic` 引用，确认仅 `sandbox.ts` 为真实断裂（其余为 basename 子串误报）。

### 踩坑经验

1. **`require()` 是 `tsc` 的绝对盲区** — 删除「看似无人引用」的模块前，必须用能解析动态 specifier 的检查（`check_module_resolution.py`）复核，不能只看静态 import 图；Node 的 `require(id: string) => any` 签名让类型系统完全无法兜底；
2. **可达性扫描 ≠ 安全检查** — 静态扫描器漏掉动态加载时会静默产出「安全可删」的假结论，且失败被推迟到运行时（表现为 500），代价远高于扫描器本身的局限；
3. **门禁必须真的运行**：本仓所有质量门禁原先只挂 `on: pull_request`，而团队直提 `main`（3408 个 commit 仅 2 个 squash 标记），因此这类断裂不会被任何门禁拦截 —— 现已补 `push: main` 触发。

---

## BUG-AGENT-2026-09-17-002: Memory Doctor「纪律默认恢复」静默吞掉归档失败并汇报为成功

| 属性 | 值 |
|------|-----|
| 发现日期 | 2026-09-17 |
| 修复日期 | 2026-09-17 |
| 严重程度 | P1（数据治理动作向用户谎报成功，运维不可观测） |
| 影响范围 | `myrm-agent-server/app/services/memory/diagnostics/diagnostic/diagnostic_repair_executor.py` |
| 出现次数 | 1 |
| 关联 | `tests/api/memory/test_capacity_theater_doctor_integration.py` |

### 现象

Memory Doctor 执行 `restore_disciplined_defaults`（纪律默认恢复，会把未锁定记忆归档以恢复预算纪律）时，即使归档全部失败，返回消息仍是朴素的成功文案：`Restored disciplined defaults: archived 0 memories, preserved 0 pinned entries.`，GUI 与审计看不到任何失败信号。

### 根因

归档循环体用裸 `except Exception: pass` 包住整个类型扫描与逐条归档：

```python
try:
    items = await self._memory_manager.list_memories(mtype, limit=100)
    for item in items:
        ...
        await self._memory_manager.update_memory(item_id, status=MemoryStatus.ARCHIVED)
        archived_count += 1
except Exception:
    pass
```

任一 `list_memories` 或 `update_memory` 抛错（如向量库不可用、记忆条目损坏）都会被静默丢弃，`archived_count` 停在 0 但 `status="completed"` 照常上报 —— **把「部分/全部失败」伪装成「已完成」**，用户无从察觉治理未生效。

### 修复

拆分为分层捕获 + 可观测上报：

1. **列表失败与单条归档失败分开捕获**，分别 `logger.warning(..., exc_info=True)` 并累加 `failed_count`；
2. **失败计数进入面向用户的消息**：有失败时追加 `(N entries could not be archived; see server logs.)`，让 GUI 不再谎报成功；
3. **保留「单条失败不中断整轮清扫」语义**（一个坏条目不应阻止其余记忆的治理），仅把沉默换成显式上报；
4. 空 `item_id` 明确 `continue` 并计为失败，不再落入宽泛捕获。

### 验证

- `tests/api/memory/test_capacity_theater_doctor_integration.py` **5 passed**（新增 `test_restore_disciplined_defaults_reports_partial_failures` 断言失败必须出现在消息中）；
- memory 全量套件 `tests/services/memory` + `tests/api/memory` **678 passed / 0 failed**；
- 真实 API 闭环 `POST /api/v1/memory/command-center/diagnostics/repairs`（dry_run / execute）实测正常。

### 踩坑经验

1. **裸 `except Exception: pass` 在「向用户汇报结果」的路径上是缺陷而非容错** — 它把可恢复错误与致命错误一视同仁地抹掉，让「治理动作」变成不可观测的黑盒；治理类逻辑必须让失败可见（计数 + 日志 + 消息），哪怕选择继续执行；
2. **宽泛 try 的作用域过大** — 原代码的 try 同时罩住「列取」和「逐条写入」两种失败语义，无法区分；应先缩小作用域再决定各自的降级策略。

---

## BUG-AGENT-2026-09-17-003: Next 隔离 lane 将构建产物路径写入被追踪的 tsconfig.json（门禁瞬态假红 + 污染入库）

| 属性 | 值 |
|------|-----|
| 发现日期 | 2026-09-17 |
| 修复日期 | 2026-09-18 |
| 严重程度 | P1（CI 门禁瞬态假红；脏 glob 可被提交进共享配置） |
| 影响范围 | `myrm-agent-frontend/tsconfig.json`（及新增 `tsconfig.base.json`）、`scripts/dev/isolated_runtime/`、`scripts/dev/workspace_hygiene.py` |
| 出现次数 | 反复（每个 E2E lane 启动都会触发） |
| 关联 | `myrm-agent-frontend/scripts/check_fractal_docs.py`、`strip_isolated_tsconfig.py` |

### 现象

1. 只要有任何 E2E 隔离 lane 存活，前端 fractal 文档门禁就会**瞬态变红**，报告 `tsconfig.json include must not list .next-isolated-* paths`；
2. `tsconfig.json`（**被 git 追踪的共享文件**）里出现 `.next-isolated-memdoc-c1`、`agentcap` 等具体 lane 宽字符 glob，最后退出的 lane 会把自己的路径留在提交内容里。

### 根因

每个私池 lane 通过 `MYRM_NEXT_DIST_DIR=.next-isolated-<id>` 启动 Next，而 Next 的 `writeConfigurationDefaults` 会把该 dist 路径当「必需 include」写回**同一个共享 `tsconfig.json`**（`getTypeDefinitionGlobPatterns(distDir)`）。由于 tsconfig 是被追踪的共享文件，写入即污染 + 门禁假红。

### 修复（结构性根治，非加检查）

关键发现：Next 的 `writeConfigurationDefaults` 在 tsconfig 声明了 `extends` 或 `references` 时**直接 return，完全跳过配置重写**。因此把 `compilerOptions` 拆到 `tsconfig.base.json`，让 `tsconfig.json` 用 `extends` 继承 —— 写入目标消失：

- `tsconfig.json` 只保留 `extends` + `include`（+ `exclude`），不再被 Next 写入；
- `tsconfig.base.json` 承载 `compilerOptions`（含 `paths` 别名）。

`next-env.d.ts` 无此逃生门（Next 无条件重写，不读 tsconfig），仍由 `strip_isolated_tsconfig.py` + `workspace_hygiene.heal_isolated_tsconfig` 在栈启动时自愈。

### 验证（全部实测，非推断）

- **写入侧**：直接调用 Next 16.3.0 的 `writeConfigurationDefaults` —— 无 `extends` 时注入 **2** 条 lane glob，有 `extends` 时注入 **0** 条；
- **读取侧**：调用 Next 真实读取链 `getTypeScriptConfiguration` → `ts.parseJsonConfigFileContent`，`paths` 正确解析出 `{"@/*":["./src/*"],"#locales/*":["./locales/*"]}`，别名未丢；
- **线上真实性**：dev server 重新编译后 `/` 返回 **HTTP 200 且真实渲染**（非 500 页）；
- **免疫力**：在 **6 个 lane 同时存活**时 `tsconfig.json` 的 `include` 中 lane 路径数 = **0**，`check_fractal_docs.py` **exit 0**；
- 私池 runtime 相关测试 **43 passed**。

### 踩坑经验

1. **「加检查」不是治本** — 原先的做法是让门禁禁止 tsconfig 出现 lane 路径 + teardown 时 strip，但污染源（Next 的配置重写）仍在，且并行 lane 会让 strip 时序竞态（谁最后退出谁写脏）。正解是**让共享文件不可被写**，从源头消灭竞态；
2. **调试 Next 行为要读它自己发布的代码**：`writeConfigurationDefaults` 顶部 `if ('extends' in userTsConfig || 'references' in userTsConfig) return;` 这个逃生门没有文档宣传，只能从源码/实测得到；结论必须用 Next 真实模块跑出来，不能凭「应该支持」下判断；
3. **被追踪的共享配置 + 并行隔离构建 = 结构性冲突**：任何「多个进程写同一份版本控制文件」的设计，最终都会表现为随机假红与脏提交。

---

## BUG-AGENT-2026-09-17-004: 400 行预算强制门禁无法执行其声称职责（台账被反复重写至失去信号）

| 属性 | 值 |
|------|-----|
| 发现日期 | 2026-09-17 |
| 修复日期 | 2026-09-18 |
| 严重程度 | P1（质量门禁长期失效，技术债静默累积） |
| 影响范围 | `.github/workflows/{frontend-build,server-fractal-docs,desktop-fractal-docs}.yml` · `myrm-agent-server/scripts/ci/run_architecture_gates.sh`（含 pre-push 钩子）· `myrm-agent-desktop/scripts/check-fractal-docs.ts` · 三端 `file_line_budget_baseline.txt` |
| 出现次数 | 反复（每次基线漂移都会再红一次） |
| 关联 | `BUG-AGENT-2026-09-17-003`（同批次暴露的门禁失效问题） |

### 现象

1. `check_file_line_budget.py` 在 `main` 上长期变红：前端报告 **46 个文件**超 400 行，且**全部**不在豁免台账中（`in baseline: 0`）。
2. 台账 `file_line_budget_baseline.txt` 自 **2026-08-15** 后再未更新，期间 46 个文件越线无人登记。
3. 该门禁的失败信息**自己就宣传逃生命令** `--write-baseline`。

### 根因

1. **门禁语义是「相对基线的棘轮」而非绝对红线**：它比对「当前超限集」与「人工维护的台账」，只对新增超限报错；但台账从未随代码增长同步刷新，于是存量越线全部计为「新增」。
2. **逃生命令让门禁自我消解**：台账被反复重写 **13 次**（最后一次一次性豁免 224 条、最大行数达 2168）。一个**要么常绿、要么一条命令就变绿**的门禁不产生任何信号，只消耗 CI 并阻塞合并。
3. **叠加 `BUG-AGENT-2026-09-17-003` 的同类问题**：门禁只挂 `on: pull_request` 而团队直推 `main`，因此「台账漂移」这件事本身也从未被任何门禁拦截。

### 修复

1. **退役强制阻断**：从 `frontend-build.yml`、`run_architecture_gates.sh`（含 pre-push 钩子）与 desktop 分形门禁中移除 400 行预算步骤；
2. **脚本降级为本地自查工具**：`check_file_line_budget.py` 与三端台账文件均保留，供开发者自查与磁盘/规模盘点，但**不再阻断 CI**；
3. **文件规模回归评审指南**：遵循 `CONTRIBUTING.md`（期望 ~400 行，超 ~500 行才需拆分）——规模问题交由 code review 与本地自查处理，而不是混进 CI 红灯；
4. **文档同步**：`ARCHITECTURE.md`、`myrm-agent-frontend/scripts/_ARCH.md`、desktop `_ARCH.md` 均改为「本地自查工具（非 CI 阻断）」。

### 验证

- 三端 CI 步骤列表实测不含 `check_file_line_budget`（`rg` 0 命中）；
- 前端 4 个仍生效门禁（`check_fractal_docs` / `check_barrel_exports` / `check_typescript_strict` / `check_module_resolution`）全部 PASS；
- desktop 门禁输出已不含 line budget 文案；
- 本地自查工具仍可正常运行（`--write-baseline` 保留）。

### 踩坑经验

1. **台账式豁免门禁天然会失效** —— 失败信息一旦宣传逃生命令，台账就会被反复重写直至失去意义；
2. **门禁应当只看仓库受控内容** —— 凡依赖「人工维护的台账 + 可一键重写的豁免」的规则，都不适合作为阻断式 CI 判据；这类「软约束」应作为本地自查；
3. **区隔「风格/文档」与「真 bug」** —— 行数只影响可读性、不影响运行正确性；把它接进 CI 会把两类性质不同的问题混在同一道红灯里，导致真 bug 被「噪声红灯」稀释；
4. **退役门禁同样要更新文档与文档断言**，否则「文档说 CI 阻断、实际已移除」会形成新的漂移（本次已同步 `ARCHITECTURE.md` 与三处 `_ARCH.md`）。

---

## BUG-AGENT-2026-09-17-005: 全套质量门禁只挂 `pull_request`，而团队直推 `main` → 门禁从未运行

| 属性 | 值 |
|------|-----|
| 发现日期 | 2026-09-17 |
| 修复日期 | 2026-09-18 |
| 严重程度 | P1（所有质量门禁形同虚设，任何断裂都无人拦截） |
| 影响范围 | `.github/workflows/{frontend-build,server-architecture,server-fractal-docs,desktop-fractal-docs}.yml` · `scripts/ci/install-pre-push-hook.sh`（本地亦无前端执行点） |
| 出现次数 | 持续存在（自门禁引入起） |
| 关联 | `BUG-AGENT-2026-09-17-001`（悬空 import 未被拦截）· `-003`（tsconfig 假红）· `-004`（台账漂移）——三者能长期潜伏都因本缺陷 |

### 现象

1. 前端 5 个质量门禁在 `main` 上**长期变红**却无人处理；`BUG-AGENT-2026-09-17-001` 的悬空 import 能一路进入 main 并导致全站 500。
2. 前端 400 行台账自 **2026-08-15** 后漂移一个月（46 个文件越线未登记）而无人察觉。
3. `check_fractal_docs.py` 的 tsconfig 假红反复出现，也没有任何自动化反馈闭环。

### 根因

1. **4 个质量门禁全部只配 `on: pull_request`**，但本仓真实交付路径是**直推 main**：实测 **3408 个 commit 中仅 7 个 merge commit、仅 2 个带 `(#N)` squash 标记**，最近 300 个 commit 里 **154 个**是 `Co-authored-by: Cursor` 的本地 agent 提交。→ CI 从未被触发，门禁从未运行。
2. **旁证（既有约定）**：仓库根的 `pr-hygiene.yml` 是**唯一**同时配了 `push: branches: [main]` 的工作流 —— 说明「push main 触发」本是本仓既有约定，只是这 4 个质量门禁漏配。
3. **本地也无兜底**：`scripts/ci/install-pre-push-hook.sh` 安装的 pre-push 钩子只执行 `run_architecture_gates.sh`（**仅 server 门禁**），前端门禁在本地没有任何执行点。

### 修复

1. **补全触发器**：4 个质量门禁均加 `push: branches: [main]`，与既有 `pr-hygiene.yml` 约定对齐；
2. **保持作用域一致**：新增的 `push.paths` 逐条复制原 `pull_request.paths`，确保两个事件运行完全相同的检查范围，不引入新的「只在某事件下才会跑」的盲区；
3. **保留分支保护路径**：`pull_request` 触发器原样保留，分支保护 / PR 校验流程不受影响。

### 验证

- 4 个 workflow YAML 均可被解析，实测触发键为 `['pull_request', 'push']`；
- `push.branches` 实测为 `- main`，path filter 与对应 `pull_request.paths` 逐条一致；
- 静态契约 `scripts/dev/tests/test_*_static.py` **269 passed**。

### 踩坑经验

1. **CI 门禁必须与团队真实交付路径一致**：如果团队直推 main，`on: pull_request` 等于**从未运行**。配置门禁时不能只写「标准做法」，必须先确认团队实际怎么合并代码；
2. **门禁配好后必须实测触发过一次**，而不是假定它生效 —— 本次是「配置文件看起来完全正确、但从未执行」的典型静默失效；
3. **排查「为什么这个 bug 没被拦住」时，优先验证门禁到底跑没跑**，而不是先怀疑规则不够严：本次三个独立缺陷（`-001`/`-003`/`-004`）能同时长期潜伏，共同原因就是门禁根本没运行；
4. **本地钩子覆盖不全会造成同样的盲区**：`install-pre-push-hook.sh` 只跑 server 门禁，因此即使开发者勤于本地校验，前端断裂依然可以直接进 main。

---

## BUG-AGENT-2026-09-18-006: `tsconfig` include 全量 glob 生成目录，导致 `check_typescript_strict` 随机假红（flaky gate）

| 属性 | 值 |
|------|-----|
| 发现日期 | 2026-09-18 |
| 修复日期 | 2026-09-18 |
| 严重程度 | **P2（门禁可反复性失效：同一代码随机红/绿，会逐渐被团队当成噪声忽略）** |
| 影响范围 | `myrm-agent-frontend/tsconfig.json`；`scripts/check_typescript_strict.py`（`frontend-build.yml` CI 阻断项） |
| 出现次数 | 任意次（取决于 i18n 生成写入与门禁扫描的时间竞态） |
| 关联 | `BUG-AGENT-2026-09-17-003`（同属「瞬态文件状态污染门禁」族）· `-004`/`-005`（门禁失去信号） |

### 现象

同一条 `python3 scripts/check_typescript_strict.py` 在相隔数分钟、代码未变的情况下给出**相反结论**：先返回 `FAIL(1)`，复跑即 `OK (strict errors 65, baseline 489)`。

### 根因

1. `tsconfig.json` 的 `include` 含 `locales/**/*.json`；
2. 而 `locales/namespaces/` 是 **`.gitignore` 忽略的生成目录**（`.gitignore:35 /locales/namespaces/`），当时含 **3157 个 JSON**，由 i18n 生成脚本持续写入；
3. 失败运行的实际报错是 **6 条 `TS6053: File ... not found`**，目标均为生成中的 `locales/namespaces/**`（如 `ko/settings/workspaceRules.json`、`zh-TW/settings/webPushTestSent.json`）——文件在扫描瞬间被生成器替换/重建；
4. `check_typescript_strict.py` 用 `_ERROR_RE = re.compile(r"error TS\d+")` **无差别计数**（第 19、31 行），无法区分「生成竞态导致的临时缺失」与「真实类型错误增加」，于是把前者误判为门禁回归；
5. `include` 中的 `locales/**/*.json` 在 `tsconfig.base.json` 拆分**之前就已存在**，故本缺陷与拆分无关，属既有隐患；`incremental: true` 生成的 `tsconfig.tsbuildinfo` 会缓存绝对路径，进一步放大不确定性。

### 修复

`tsconfig.json` 的 `include` 由 `locales/**/*.json` 收窄为 **`locales/*.json`**，即只类型检查 6 个**被 git 追踪**的顶层 locale 文件。

覆盖面未损失：`src/**` 对所需 namespace JSON 的静态 `import`（`src/i18n/locale-manifest.ts` → `n/manifest.json`、`src/lib/local-backend-dev.ts` → `n/{en,zh}/common.json`、`src/lib/metadata/static-metadata.ts` → `n/zh/metadata.json`、`src/lib/i18n/streamNotificationCopy.ts` → `n/*/notifications.json`）仍会被 TypeScript 自动纳入程序，只是不再全量 glob 生成物。

### 验证

- 收窄前后 `check_typescript_strict.py` 错误数**完全一致（65）**，证明 3157 个生成文件对类型检查零贡献；
- 收窄后复跑门禁 `OK (strict errors 65, baseline 489)`；
- `git diff` 确认仅 1 行 include 变更，无其他副作用。

### 踩坑经验

1. **`include` 绝不能 glob `.gitignore` 忽略的生成目录**：生成器与门禁并发时必然产生瞬态 `TS6053`，门禁失去可反复性；
2. **门禁计数必须区分「环境噪声」与「真实回归」**：`error TS\d+` 这类无差别正则会同时吞掉两类信号，应至少对 `TS6053` 做存在性甄别或排除未追踪路径；
3. **排查「门禁随机红」优先怀疑瞬态文件状态**（生成目录、buildinfo、lock、dist），而不是先怀疑代码回归——同一命令跑出两种结论本身就是最强的「非确定性」证据。

---

## BUG-AGENT-2026-09-29-001: Chrome E2E 会话路由 404 漂移与审批弹窗阻挡

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-09-29 |
| 修复日期 | 2026-09-29 |
| 严重程度 | P1（阻塞 Chrome E2E / Dev Gate / CDMCP Mux 回归） |
| 影响范围 | `myrm-agent-frontend/next.config.ts`, `scripts/dev/lib/cdp_chat/support.py`, `myrm-agent-server/app/services/meeting_notes/service.py`, `tests/support/chrome_mcp_e2e.py` |
| 出现次数 | 1（已彻底修复并通过端到端物理对账） |

### 现象

1. **会话路由 404 漂移**：Chrome E2E 测试及 Dev Gate 在通过 CDP 访问或探测 `/chat/{chatId}` 时，前端 Next.js 页面返回 `404: This page could not be found`，导致会话页面加载超时假死；
2. **遗留审批模态弹窗遮挡**：Settings 或 Chat 页面加载后，顶层被历史并发用例残留的 `批量审批 (7 个工具)` 弹窗覆盖，阻挡后续 UI 点击断言；
3. **会议纪要与 Wiki 发布契约泄露**：`publish_meeting_notes` 偶发报告绝对本地路径而非 Vault 相对路径，且在并发大模型推理时 30s 默认超时不足造成偶发 `TimeoutError`。

### 根因

1. 前端真实动态会话路径为根级别 `src/app/[chatId]/page.tsx`，而 `next.config.ts` 的 `rewrites()` 缺少针对 `/chat/:chatId` 的动态重写规则，且测试端 `support.py` 的正则仅支持根路径匹配；
2. 测试端的弹窗规避脚本 `DISMISS_MODALS_JS` 仅匹配了常见的单次关闭按钮（Dismiss/Skip/稍后再说），未覆盖 `全部拒绝|Reject all` 这类批量审批操作，导致批量审批悬挂弹窗无法被自动清退；
3. `publish_meeting_notes` 在处理 `RawPublishResult` 时错误地对对象进行了直接字符串化（`str(published)`），导致内部绝对路径泄露；并且 `http_json` 硬编码 30.0s 超时时间，不适应高负载大模型提炼请求。

### 修复

1. **会话路由重写与正则泛化**：
   - `next.config.ts`: 在 `rewrites()` 中添加 `{ source: '/chat/:chatId', destination: '/:chatId' }`；
   - `support.py`: 更新 `_CHAT_ID_PATH_RE` 兼容可选的前缀 `/chat/`；
2. **批量审批自动规避**：
   - `support.py`: 在 `DISMISS_MODALS_JS` 的按钮文本正则中增加 `|全部拒绝|Reject all`；
3. **发布契约与超时解耦**：
   - `service.py`: 严格按强契约返回 `[published.relative_path] if published.written else []`，拦截安全拦截或跳过的产物并隔离绝对路径；
   - `tests/support/chrome_mcp_e2e.py`: `http_json` 增加 `timeout_sec` 参数，支持耗时路由传入 90s 超时；
   - 统一规范 settings 子路由尾部斜杠归一化 `_normalize_settings_url`。

### 验证

1. `curl -s -I http://127.0.0.1:3000/chat/c-test-12345` 响应 `HTTP/1.1 200 OK`；
2. `test_turn_flow_smoke.py` 14 个测试全通；
3. `test_browser_takeover_chrome_e2e.py` 全量 4 个测试（含真实模型 LIVE SHPOIB 隔离后端会话流）100% 物理通过（Exit Code 0，169s 完成）；
4. `test_meeting_notes_service_coverage.py` 覆盖单测全绿。

### 踩坑经验

1. **动态路由别名必须配置双向对齐**：当产品根路径存在动态参数匹配（`/[chatId]`）而测试/外部深链约定使用语义化前缀（`/chat/:chatId`）时，必须在 Next.js `rewrites()` 声明动态重写，不可仅依赖静态页面；
2. **测试环境模态弹窗规避必须涵盖所有阻断类型**：不能只考虑业务级 onboarding 引导页，还要将安全/审批系统的强阻断弹窗（全部同意/全部拒绝）纳入自动兜底清理规则；
3. **契约字段与返回对象解耦**：发布类服务返回的路径绝不能直接调用 `str(obj)`，必须显式提取相对路径属性（如 `relative_path`），避免因对象表示方法变更泄露环境物理路径。

---

## BUG-AGENT-2026-10-08-001: 本地模型连通性测试与每日回顾的超时从未生效（限制写在 `config` 里到不了提供方）

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-08 |
| 修复日期 | 2026-10-08 |
| 严重程度 | P2（挂起的模型端点让设置页测试与每日回顾无限期等待，设置页只显示不带原因的失败） |
| 影响范围 | `myrm-agent-server/app/api/config/router.py`（`POST /config/test-local-model`）, `myrm-agent-server/app/api/statistics/daily_wrap.py`, `myrm-agent-server/app/api/integrations/llms.py`（文档）, `myrm-agent-frontend/src/services/llm-config.ts`（注释） |
| 出现次数 | 1 |
| 关联 | harness `BUG-HARNESS-2026-10-08-004`（根因与框架侧修复） |

### 现象

1. 设置页「隐私路由 → 本地模型 → 测试」对挂起的端点：页面在 15 秒后自行中止请求，只弹出不带原因的“连接失败”；服务端侧没有任何截止时间，等待只受模型自身的 300 秒超时约束；
2. 每日回顾生成遇到停滞的轻量模型：请求一直打开，客户端在 30 秒后中止；服务端侧同样没有截止时间；
3. 代码里写着“5 秒超时、`max_tokens=1`”与“15 秒超时、`max_tokens=500`”，文档还写着“1-token 探活”，实测并不生效。

### 根因

`llm.ainvoke(messages, config={"max_tokens": ..., "timeout": ...})` 的 `config` 是 LangChain 的 RunnableConfig，不是模型调用参数。实测到达提供方的是 `max_tokens=4096`、`force_timeout=300.0`。

### 修复

1. `/test-local-model`：`asyncio.wait_for` 12 秒截止（低于设置页的 15 秒中止）；到期返回“No response within 12 seconds — the model may still be loading, or check the server address”，与提供方侧的“Connection timed out — check the server address”区分（模型冷启动与地址错误在 12 秒内表现相同，不能只指责地址）；失败日志改记异常类型，避免空消息；
2. `daily_wrap`：`asyncio.wait_for` 60 秒截止；到期转为 408 `timeout_error`，因为裸 `TimeoutError` 会被 `_classify_exception` 归为 `Database operation timeout`（去掉转换的变异实测：500 `Get daily wrap failed: Database operation timeout`）；
3. 不强制 `max_tokens`：推理模型会拒绝过小的输出预算，成本由截止时间约束；
4. 修正“1-token 探活”的 docstring、测试说明、前端注释与 `_ARCH.md`。

### 验证

1. 新增 `tests/api/config/test_local_model_endpoint.py`（4 个）、`test_daily_wrap.py` 与 `test_daily_wrap_integration.py` 各 1 个；去掉截止时间的变异使 3 个超时用例全部失败，去掉 408 转换的变异使 2 个每日回顾用例失败，去掉到期分支的变异使到期用例失败，把所有超时都报成到期的变异使提供方超时用例失败；
2. 受影响的 4 个测试文件共 56 个用例通过；
3. 真实套接字实验（litellm、OpenAI SDK 与本地挂起的 HTTP 服务，没有任何 mock）：端点 12.10 秒返回失败消息；返回后 0.01 秒服务端观察到对端关闭连接，说明取消真正到达套接字；随后对正常服务的再次调用成功；对照组中适配器自身在 15 秒时仍未返回。

### 踩坑经验

1. 给模型调用加时间上限只能靠模型构造参数或 `asyncio.wait_for`，`config=` 不是调用参数；
2. `TimeoutError` 直接交给 `internal_error()` 会被报成数据库超时，LLM 截止必须在边界处转成 `timeout_error`；
3. 12 秒与 60 秒是按设置页 15 秒中止与客户端默认 30 秒超时取的设计值，没有时延分布数据；服务端依赖已发布的 harness 版本，`/check-reachability` 的真实截止时间要等 harness 升版后生效。

---

## BUG-AGENT-2026-10-13-001: 上一轮晚于下一轮收尾，清掉新一轮的运行状态（停止按钮消失或失效）

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P2（新一轮仍在运行，界面却显示空闲：停止按钮消失或点击无效，服务端继续跑到结束，手动重发被服务端以忙碌拒绝） |
| 影响范围 | `myrm-agent-frontend/src/store/chat/messageRequest.ts`（`sendMessage` / `attachToChat` 的 `finally`）, `sendLifecycle.ts`, `streamConsumer.ts` |
| 出现次数 | 1（真实 store + 真实请求管线复现，未取得线上遥测） |
| 关联 roadmap | `topic_09_frontend_ux_roadmap`（dev-shell 内部 roadmap，未归档进本仓） |

### 现象

1. 一轮的流结束后，`MESSAGE_END` 的 50 ms 定时器已让界面回到空闲，但这一轮还在 `finalizeAgentStreamTurn` 里向服务端对账；这段时间内用户或排队出队（界面空闲 300 ms 后发送）发出的下一轮，会在对账返回后被上一轮的 `finally` 清掉 `loading`、Stop 句柄、请求 id、输入框附件和面板句柄；
2. 下一轮其实还在跑：停止按钮消失或点击无效（`stopMessage` 找不到句柄），服务端继续跑到结束，再次发送会被服务端以忙碌拒绝；
3. 另外两条同构路径：停止了一个正在退避重试的请求并发出新一轮，旧轮的退避等待不响应停止，等待结束放弃时清掉新一轮；`attachToChat` 重连收尾的对账同样晚于下一轮。

### 根因

回合没有「归属」：`finally` 无条件复位共享状态，而这些状态同一时刻只能属于一轮。上一轮的收尾发生在它的流之后（对账、退避等待结束、attach 对账），下一轮可能已经接管。`sendMessage` 里原有的 `currentSessionMessageId === requestMessageId` 守卫排在同一个 `finally` 的无条件清空之后，对当前活动的 store 不起作用，`attachToChat` 回合又没有请求 id。

### 修复

1. `sendLifecycle.isHeldByOtherTurn(held, own)`：共享 Stop 句柄是另一轮的存活 `AbortController` 才算被别轮持有；`null`、缺失，以及面板快照（JSON 克隆）里的普通对象句柄都算无人持有，后台面板里失败的回合仍然释放快照；
2. `sendMessage` 与 `attachToChat` 的 `finally` 以本轮自己的 `AbortController`（在 `try` 之前创建，登记为共享 Stop 句柄）为身份：被别轮持有时，不动 `loading`、Stop 句柄、请求 id、附件和面板句柄；`scheduleAutoSave` 与处理锁释放照常；删除空转的守卫；
3. 顺带把 `shouldUseMultiplexedAgentStream` 的两份相同拷贝收敛为 `streamConsumer.ts` 的一个导出（请求体与消费端必须同一答案；行为与请求体不变，属于维护性清理，不是用户可见修复）。

### 验证

1. 新增 `messageRequest.turnOwnership.test.ts` 6 个用例（真实 `useChatStore` / `useWorkspaceStore` 与真实请求管线，只替换网络与对账接口）、`messageRequest.queueSemantics.test.ts` 的 2 个纯函数用例和 `streamConsumer.transport.test.ts` 3 个用例（固定请求体与消费端共用的 multiplex 判定）；修复前 4 个管线用例红且原因是 `loading` 被清成 false（晚对账有/无面板各 1、停止后退避结束 1、attach 1），当前回合释放与后台面板快照 2 个用例修复前后都绿（`BUG-AGENT-2026-10-13-006` 之后，「停止后退避结束」一例改写为停止立即安静结束的用例，并新增一个多路复用管线用例，该文件现为 7 个用例）；
2. 变异检查（逐个应用后恢复，文件哈希与基线一致）：总是释放 → 5 红；缺失句柄当别轮 → 2 红；面板句柄不受守卫 → 1 红；别轮收尾仍清附件 → 2 红；别轮收尾仍清请求 id → 2 红；attach 守卫去掉 → 1 红；multiplex 判定恒为 true → 1 红（仅直连标记用例）；无 window 时不走 multiplex → 1 红（仅无 window 用例）；
3. 把 `finally` 里的两处判定分别改成恒为 false（等价于无条件释放），`turnOwnership` 用例各自变红：`sendMessage` 处 3 红、attach 处 1 红；附件列表复位不受守卫 → 2 红（仅晚对账用例），去掉复位 → 1 红（仅当前回合释放用例）；每次恢复后哈希与基线一致；
4. `src/store/chat` 84 个文件 567 个用例，以及 `store/__tests__`、`hooks/message-input`、`lib/approval` 与 2 个 resumeRefusal 组件用例 61 个文件 510 个用例，全部通过；
5. oxlint 0 条（用带 `debugger` 的草稿文件做过正向对照，确认静默即无告警）；全量 `tsc --noEmit` 只剩他人未跟踪文件 `kanban/__tests__/KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误，本修复涉及的文件无错误。

### 踩坑经验

1. 共享的回合状态只能由持有者释放，`finally` 里的复位必须带身份判断；身份不能用请求 id（attach 回合没有 id，`clearActiveStream` 也会清掉 id），要用 Stop 实际使用的控制器句柄；
2. 面板快照是 JSON 克隆，克隆出的句柄是普通对象：严格相等会把「无人持有」当成「别轮持有」，后台面板里的回合就永远释放不了，必须用 `instanceof AbortController`；
3. 这类竞态要用真实 store 和真实请求管线复现，mock 掉 `setMessages` 看不到「别轮的状态被清掉」；
4. 局限：没有线上遥测，云端对账耗时与命中频率未测；本机 30 次对账耗时 41–458 ms（中位 57 ms，p90 126 ms），按此推算约 7% 的排队出队会撞上晚收尾（推算，不是实测命中率）；真实浏览器里的分栏窗格组合、`streamConsumer.ts` 中 attach 嵌套（`allowWhileLoading`）只做了代码推演，没有端到端复现。

---

## BUG-AGENT-2026-10-13-002: 设置页深链没有单一真源，提示 / 推送 / 技能资产里的“去设置”落到 404 或错误页面

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P2（用户按提示去重新授权或查看治理结果时落到 404 页面或无关页面；功能本身未受损） |
| 影响范围 | 前端 `settingsRoutes.ts`（新增）、`app/settings/[tab]/page.tsx`、`SettingsLayout.tsx`、`SettingsMenu.tsx`、`useSettingsDirtyStore.ts`、`useDirtyGuard.ts`、`scripts/verify-i18n.mjs`、`NavBar.tsx`、`ExtensionDisconnectedBanner.tsx`、`DailyReviewCard.tsx`、`SkillRequiredConnectorsPreflightBanner.tsx`、`DataFlowDisclosurePanel.tsx`、`integrationOAuthDisplay.ts`、`hooks/globalEvents/useGlobalEvents.ts` 与 `reauthToasts.ts`（新增）、`useConfigErrorDetector.ts`、`locales/*.json`；服务端 `app/core/web_push/push_deep_links.py`、`app/services/wiki/maintain/runner.py`、`app/services/wiki/daily_review/runner.py`、`app/core/channel_bridge/agent_executor/execute_errors.py`、预置技能 `mcp-expiry-watchdog` 与 `mcp-proactive-reauth-watchdog` |
| 出现次数 | 2（同类根因见 `BUG-AGENT-2026-07-27-001`：Tab 多处登记遗漏） |
| 关联 roadmap | `topic_19_cross_device_mobile_remote_and_physical_companion_roadmap`（dev-shell 内部 roadmap，未归档进本仓） |

### 现象

1. 直接访问或刷新 `/settings/workbench`、`/settings/shares` 走 `notFound()`：两个 Tab 已在 `SettingsLayout` 的 `BASE_TABS` 与 `SettingsMenu` 登记（HEAD `SettingsLayout.tsx:132,139`、`SettingsMenu.tsx:116,149`），`page.tsx` 的 `VALID_TABS` 却没有它们；
2. 站内与服务端写死的入口指向不存在的路由；运行中的 dev server 上 `/settings/browser`、`/settings/knowledge`、`/settings/extensions` 的响应体均含 `NEXT_HTTP_ERROR_FALLBACK;404`：导航栏与 `ExtensionDisconnectedBanner` 的扩展入口（`/settings/browser`）、`DailyReviewCard` 的待审编辑入口与每日回顾 / 知识库治理 cron 文案里的链接（`/settings/knowledge…`）、MCP 授权过期 toast 的操作按钮（`/settings/extensions`）；
3. 预置技能 `mcp-expiry-watchdog`、`mcp-proactive-reauth-watchdog` 让模型把用户指向 `/settings/integrations?focus=google-workspace` 与 `/settings/integrations?reauth=google`，这个路由同样不存在；
4. OAuth 过期（`OAUTH_REAUTH_REQUIRED`）的 Web Push 与站内 toast 都落到「连接新服务」的目录页 `/settings/integrationCatalog`，数据流披露面板里每个已连接的 OAuth 账号也链到它；前置检查横幅按 `issuer.includes('google')` 在 Credentials 与 Skills 之间二选一；模型提供商的 OAuth（issuer 以 `provider_` 开头）本应去 Models；
5. 六个语言文件都缺 `metadata.settingsTabs.{workbench,shares,a2aPeers}` 与 `settings.menu["brand-studio"]`（逐文件脚本核对 HEAD），修复前实测 `/settings/a2aPeers` 的页面标题是原始 key（其余三个未逐一实测）；
6. `execute_errors.py` 的 `config_url: "/settings/model-service"`（路由不存在）与 `useConfigErrorDetector.ts` 的 `config_url` 是无人读取的死字段（全仓 `config_url` 检索无消费方）。

### 根因

1. Tab 清单在 4 个文件里手抄了 6 份：`page.tsx` 的 `VALID_TABS` 与 `DEPRECATED_TAB_MAP`、`SettingsLayout.tsx` 的 `BASE_TABS` 与另一份 `DEPRECATED_TAB_MAP`、`SettingsMenu.tsx` 的 `SettingsTab` 联合类型、`verify-i18n.mjs` 的 `VALID_TABS`；新增一处不会被其余感知，两份别名表也已彼此漂移（`page.tsx` 缺 `memory-cloud-backup` / `memory-migration`，`SettingsLayout.tsx` 缺 `persona` / `toolCapabilities`）；
2. 跨层写死的 `/settings/<tab>` 字面量（前端组件、服务端推送与 cron 文案、预置技能资产）不在任何校验范围内：`verify-i18n` 只查文案键，没有测试核对“字面量指向的 Tab 存在”；`BUG-AGENT-2026-07-27-001` 当时只补了遗漏的条目，没有消除多处登记；
3. OAuth 落点把「连接新服务的目录」当成了「管理既有授权的页面」，并用 issuer 子串匹配代替显式映射。

### 修复

1. 新增 `settingsRoutes.ts` 作路由单一真源：`SETTINGS_TABS`（48 个）、`SETTINGS_TAB_REDIRECTS`（18 个别名）、`TAURI_ONLY_TABS`、`isSettingsTab`、`getSettingsTabRedirectPath`；`page.tsx`、`SettingsLayout.tsx`、`SettingsMenu.tsx` / 脏状态 store / `useDirtyGuard.ts`（只取类型）与 `verify-i18n.mjs`（读取清单）全部改读它；别名统一由服务端页面 `redirect()` 消化，`SettingsLayout` 里的客户端 `router.replace` 副本删除；`SECTION_COMPONENTS` 对 `SettingsTab` 穷尽，新增 id 漏写组件会编译报错；`SettingsLayout.tsx` 由 469 行降到 391 行；
2. 死链改正：`/settings/browser` → `/settings/extensionBridge`，`/settings/knowledge…` → `/settings/wiki…`（含服务端两个 runner 的文案），`/settings/extensions` → `/settings/mcp`（随 toast 抽出为 `reauthToasts.ts`），预置技能两处 → `/settings/mcp`；删除两个 `config_url`；
3. OAuth 落点：前端 `getOAuthIssuerSettingsPath(issuer)`（`provider_*` → `/settings/models`，其余 → `/settings/credentials`）由 toast、前置检查横幅与数据流面板共用；服务端 `push_deep_links._oauth_reauth_path` 按同一规则镜像（Web Push 不能 import 前端，两侧各由测试钉死）；提示条里的账户名由 `formatOAuthIssuerLabel` 转成可读写法（`google_workspace` → `Google Workspace`，与数据流面板同一个函数），不再展示原始 issuer id，也不转发后端写给开发者的英文 `reason`；
4. 守门：服务端 `tests/architecture/test_settings_deep_links.py` 扫描前端源码、`app/**/*.py` 与 `assets/**` 里所有 `/settings/<id>` 字面量，要求落在 `SETTINGS_TABS` ∪ `SETTINGS_TAB_REDIRECTS` 内（跳过测试源码与含 `prefix=` 的 FastAPI 路由行）；
5. 补齐六语言 `metadata.settingsTabs.{workbench,shares,a2aPeers}` 与 `settings.menu["brand-studio"]`。

### 验证

1. 前端 5 个相关测试文件 51 例通过（`settingsRoutes` 7、`reauthToasts` 6、`integrationOAuthDisplay` 13、`SkillRequiredConnectorsPreflightBanner` 7、`DataFlowDisclosurePanel` 18），与目录连接状态那批合计 11 个文件 99 例全过（JSON 报告）；`src/components/features/settings`、`onboarding`、`hooks/globalEvents`、`hooks/ui`、`lib/skills`、`components/layout` 与横幅测试共 168 个文件 1006 例全过（exit 0）；
2. 服务端 `test_settings_deep_links.py`、3 个预置技能钉死测试、`tests/core/web_push`、两个 wiki 测试文件共 98 例通过；
3. 变异检查：在前端 `src`、服务端 `app`、`assets` 各放一个探针文件，分别写 `/settings/browser`、`/settings/knowledge?wikiTab=pendingEdits`、`/settings/integrations?reauth=google`，守门测试变红并逐条报出文件与行号（`1 failed, 1 passed`），删除探针后恢复全绿；路由单测与 OAuth 落点测试没有逐个做变异；
4. 运行中的 dev server 只读 GET：`/settings/workbench`、`/settings/shares` 返回 200；别名 `/settings/persona` 的响应体含指向 `/settings/personalization` 的 `<meta http-equiv="refresh">`；`a2aPeers`、`shares`、`workbench`、`brand-studio` 的页面标题均为译文；该 dev server 读取被 git 忽略的 `locales/namespaces/`，需先 `bun run i18n:split` 重新生成才能读到新键；
5. oxlint 0 条（用带 `debugger` 的探针文件做过正向对照）；`verify-i18n` 通过；全量 `tsc --noEmit` 只剩他人未跟踪测试文件 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误。

### 踩坑经验

1. 路由 id 只能有一份清单，类型、校验脚本与别名表都从它派生；手抄副本迟早漂移，这次两份别名表已经不一致；
2. 跨层写死的字面量要有机器守门，前端、服务端与提示词资产用同一份路由真源核对，否则写错一个 id 只能等用户点到 404；
3. 落点要按用户意图选页面（管理既有授权 ≠ 连接新服务），issuer → 页面用显式映射，不要用子串匹配；
4. Next 在 `Suspense` 内的 `redirect()` 返回 200 加 `<meta http-equiv="refresh">`，不是 3xx，探针要读响应体，只看状态码与 `Location` 会误判成“没有重定向”；
5. 局限：服务端 `provider_` 前缀规则与前端各有一份（两侧测试分别钉死，不是同一份代码）；没有对真实 Web Push 载荷做端到端点击，移动端 PWA 的推送点击落点未实测。

---

## BUG-AGENT-2026-10-13-003: 集成目录不反映已连接状态，连接对话框在安全扫描期间可重复触发

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P3（已连接的服务仍引导“连接”，到保存时才被拦下；安全扫描期间按钮可重复点击；触屏看不到官网入口；繁体中文用户在引导页看到中文、点开对话框却是英文） |
| 影响范围 | `IntegrationCatalogSection.tsx`、`IntegrationConnectDialog.tsx`、`connect-dialog/AuthSection.tsx`、`ToolsConnectOnboardingStep.tsx`、`catalog-connection.ts` / `catalog-locale.ts` / `CatalogConnectionStatus.tsx`（新增）、`catalog-icons.tsx`、`locales/*.json` |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-13-002`（同一批次：设置页路由与重新授权落点） |

### 现象

1. 设置 → 集成目录里已保存（或已停用）的服务仍显示「连接」，点开填完凭证才被 `alreadyConnected` 拒绝（对话框以 `mcpConfig.name` 与已保存的 MCP 服务比对）；
2. 首次引导的「连接工具」步骤只在组件内存一份本次会话的 `connectedIds`（HEAD `ToolsConnectOnboardingStep.tsx:27`）：此前已连接的服务仍显示「连接」，「继续」按钮只看本次是否点连成功过（`:133`）；
3. 连接对话框在调用安全扫描前先 `setConnecting(false)`（HEAD `IntegrationConnectDialog.tsx:152-153`）：按钮在扫描期间既不显示「连接中」，也可以再次点击并启动第二轮扫描；
4. 官网外链图标是 `opacity-0 group-hover:opacity-100`（HEAD `IntegrationCatalogSection.tsx:220`）：触屏没有 hover，图标始终不可见，也没有可访问名称；
5. 目录语言由三处各自判断：目录区读 `document.documentElement.lang`（HEAD `IntegrationCatalogSection.tsx:75`），引导页把原始 `lang`（如 `zh-TW`）原样传给对话框（`ToolsConnectOnboardingStep.tsx:63,146`），对话框以 `locale === 'zh'` 严格比较（`IntegrationConnectDialog.tsx:47`），所以繁体中文用户在引导页看到中文卡片，点开后的说明是英文；分类标签只有中、英两张写死的表（`IntegrationCatalogSection.tsx:19,135`）。

### 根因

目录条目与“是否已保存”之间没有共享的判定：状态只存在于引导页本次会话的局部 state 与对话框提交时刻的重复校验里；`setConnecting(false)` 写在异步安全闸门之前，而 `try/finally` 本来已经兜底复位；语言判定在三处各写一份，且类型是裸 `string`。

### 修复

1. `catalog-connection.ts`：`resolveCatalogConnectionState(entry, mcpConfigs)` 以 `mcpConfig.name` 对照已保存的 MCP 服务（与对话框的重复守卫同一身份），得出 `available` / `connected` / `disabled`（`enabled === false` 为已停用），`useCatalogConnectionState()` 订阅配置 store；目录卡片与引导页共用。已连接 / 已停用的卡片以 `CatalogConnectionStatus` 状态标签加「管理」链接（→ `/settings/mcp`）取代「连接」按钮；保存成功后卡片即时转为已连接，不再重新拉取目录（目录是静态的，状态由 store 派生）；
2. 引导页：删除 `connectedIds`，行状态与「继续」按钮由 store 派生（此前已连接的服务直接显示已连接并可继续；已停用的不计为已连接）；
3. 对话框：删除探测失败、`exists`、闸门前三处提前的 `setConnecting(false)`，统一由 `finally` 复位，按钮在安全扫描全程保持忙碌；
4. `catalog-locale.ts`：`toCatalogLocale`（所有中文变体 → `zh`，其余 → `en`）与 `useCatalogLocale()`（跟随 next-intl 当前语言）；对话框与 `AuthSection` 的 `locale` 收窄为 `CatalogLocale`；
5. 分类标签改走 i18n（`settings.integrationCatalog.categories.*`，9 个键 × 六语言，`t.has` 判定，未收录的分类回退为原 id；这组键是动态读取，`verify-i18n` 看不到，由服务端架构测试 `test_catalog_category_locales.py` 按目录接口返回的分类逐语言钉住，删键与置空两种变异均被抓出），新增 `disabled` / `manage` / `openWebsite`，删除不再使用的 `boot.onboarding.toolsConnect.connected`（引导页改用目录的同一状态标签，繁中措辞随之统一为“已連線”）；官网外链在可悬停设备上悬停或键盘聚焦时显现、触屏常显，并补上带服务名的 `aria-label`；去掉卡片 className 里空的 `hover:` 残留。

### 验证

1. 6 个测试文件 48 例通过（`catalog-locale` 8、`catalog-connection` 5、`CatalogConnectionStatus` 2、`IntegrationCatalogSection` 10、`ToolsConnectOnboardingStep` 9、`ConnectDialogCredentialFlows` 14，JSON 报告）；新增用例“扫描未结束时连接按钮保持忙碌，第二次点击不会再启动一轮”让 `mockGateMcpEnable` 返回挂起的 Promise，断言按钮名为 `connecting` 且 disabled、二次点击不再调用闸门、放行后 `setMCPConfigs` 恰好一次；把 `setConnecting(false)` 放回闸门之前的变异使该用例变红，还原后变绿；
2. 与路由那批合计 11 个文件 99 例全过；`src/components/features/settings`、`onboarding`、`hooks/globalEvents`、`hooks/ui`、`lib/skills`、`components/layout` 与横幅测试共 168 个文件 1006 例全过（exit 0）；
3. oxlint 0 条；`verify-i18n` 通过；全量 `tsc --noEmit` 只剩他人未跟踪测试文件 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误；`verify-i18n-references` 的失败项来自他人未提交的功能，不含本批文件与键。

### 踩坑经验

1. “是否已连接”应从唯一数据源派生（已保存的 MCP 配置 store），不要在各处各存一份“本次会话点过”的布尔；
2. 已有 `try/finally` 兜底复位的异步流程里再手写提前复位，会让“忙碌”窗口在最长的一步（安全扫描）里消失；React 会把同步段里的 `true → false` 合并掉，界面从未显示过“连接中”，测试必须让异步步骤挂起才能复现；
3. 目录内容只有中英两份：所有中文变体读中文、其余读英文，要在一个函数里归一，不要把原始 `lang` 字符串传给下游做严格比较；
4. 悬停才显现的控件要用 `[@media(hover:hover)]` 限定，触屏默认可见，并补可访问名称；
5. 局限：没有真实浏览器里的视觉验收（触屏常显、深浅主题、手机宽度只有类名与组件测试）；连接身份按 `mcpConfig.name` 判断，用户在 MCP 页以别的名字手动添加的同一服务不会被识别为已连接。

---

## BUG-AGENT-2026-10-13-004: 开发者中心的「导入导出」页内标签与侧栏子项点击后弹回「开发者」标签

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P3（设置 → 开发者里点「导入导出」，页面立即回到「开发者」标签；该标签只能经驼峰写法的深链打开） |
| 影响范围 | `DeveloperCenterSection.tsx`、`settingsRoutes.ts` |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-13-002`（同一批次：设置页路由） |

### 现象

1. 页内标签 `value="importexport"`（`DeveloperCenterSection.tsx:93`）与侧栏子菜单项 `{ id: 'importexport' }`（`SettingsMenu.tsx:139`）都会把 `?sub=importexport` 写进地址栏（`defaultSubTabResolver` 原样输出标签值）；
2. 页面按地址栏重新选标签时只认 `sub === 'importExport'`（驼峰，HEAD `DeveloperCenterSection.tsx:32`），小写写法落进 `else` 分支被当作「开发者」标签，页面随即弹回；
3. 只有别名 `/settings/importExport`（重定向表写成 `sub=importExport`）与 `WorkbenchRetentionSection.tsx:249` 的驼峰链接能打开该标签。

### 根因

同一个子视图有两种拼写：标签值与侧栏 id 是 `importexport`，别名、深链与页面入口写 `importExport`；解析 `sub` 的 effect 只认其中一种，其余值一律回落到默认标签，没有任何地方核对“标签自己写进 URL 的值能被读回”。路由单一真源（`-002`）收拢别名表时，这一条沿用了驼峰写法，其余 14 条带 `sub` 的别名都用侧栏子视图 id。

### 修复

1. `DeveloperCenterSection` 的 `sub` 解析同时接受标签值 `importexport` 与别名写法 `importExport`（与同一函数里 `experimental` / `experimentalFeatures`、`usage` / `usageStatistics` 的处理一致）；
2. `settingsRoutes.ts` 的 `importExport` 别名改指向 `?sub=importexport`，与其余别名一样使用侧栏子视图 id；驼峰链接仍能打开该标签。

### 验证

1. 新增 `DeveloperCenterSection.test.tsx`（9 例）：对 5 个页内标签逐个做“标签写进 URL 的 `sub`（真实的 `defaultSubTabResolver`）→ 渲染后选中同一标签”的往返断言，另有 3 个别名写法与 1 个未知值回落；修复前 `importexport` 一例红（`Unable to find an element by: [data-testid="importexport"]`），其余 8 例绿，修复后 9 例全绿；`settingsRoutes.test.ts` 补一条断言钉住别名重定向目标；
2. 其余 6 个中心页（模型、技能、工具质量、记忆、通信、系统）按源码逐个比对“页内标签值 → 写进 URL 的 `sub` → 解析分支”，未发现同类不一致。

### 踩坑经验

1. 标签状态与 URL 双向同步时，要有“自己写出的值能被自己读回”的往返测试；只测“读 URL”，或把写 URL 的 Hook 整个 mock 掉再断言，抓不到读写两端的拼写分歧；
2. 同一个标识有多种拼写时，规范写法（标签值）要能被解析，别名写法只作为外部入口；
3. 局限：往返断言只覆盖 `DeveloperCenterSection`，其余 6 个中心页是源码比对；没有在真实浏览器里点过。

---

## BUG-AGENT-2026-10-13-005: 系统唤醒后，仍在运行的一轮被界面显示为空闲（停止按钮消失）

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P2（运行中的一轮在唤醒后界面显示空闲：停止按钮随 `loading` 消失，服务端继续跑到结束，用户无法从界面终止） |
| 影响范围 | `myrm-agent-frontend/src/services/desktopWakeRecovery.ts` |
| 出现次数 | 1（单测与真实 chat store 复现，未取得线上遥测） |
| 关联 | `BUG-AGENT-2026-10-13-001`（同一批次：回合归属）、`BUG-AGENT-2026-10-13-006` |

### 现象

1. 桌面端系统唤醒（Tauri `app:system-wake`）、浏览器标签页隐藏 10 秒以上后回到前台、浏览器 `online` 事件，都会让唤醒处理器进入 `ready` 阶段；
2. 处理器对任何处于 loading 的当前聊天先 `loadMessages`，再在 `finally` 里无条件 `setLoading(false)`；
3. 那一轮若仍在流式运行（store 持有它的 `abortController`），界面立刻显示空闲：停止按钮随 `loading` 消失，服务端继续运行。

### 根因

处理器把所有 loading 都当作「唤醒后残留的假死转圈」，没有区分两种来源：没有轮次句柄的残留 loading，与持有 `abortController` 的真实进行中轮次。后者的收尾归它自己的流管理（终止事件、静默看门狗、Stop），唤醒处理器无权抢先释放。

### 修复

`handleWakePhaseTransition` 只对「loading 且没有 `abortController`」的聊天重新同步消息，`loading` 由 `loadMessages` 自行结束；持有句柄的轮次不碰；删除 `finally` 里的无条件 `setLoading(false)`。历史列表刷新与后台任务通知不变。

### 验证

1. `desktopWakeRecovery.test.ts` 现 14 个用例。用 `git show 66e2a9f6f~1` 还原修复前源码运行同一测试：4 例红、10 例绿，运行后文件逐字节还原。红的 4 例是：无句柄的残留 loading 被重新同步且历史与后台任务照常刷新、持有句柄的轮次既不重新同步也不被释放、重新同步抛错时仍继续刷新历史与后台任务、真实 `useChatStore` 下运行中的轮次不受唤醒影响且 Stop 仍能到达它；修复后 14 例全绿；
2. 相关 22 个测试文件 253 个用例全绿（含本文件）；oxlint、prettier、窄范围与全量 `tsc --noEmit` 对本修复涉及的文件无问题（全量 `tsc` 只剩他人 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误）。

### 踩坑经验

1. 「loading」不是单一来源：自愈逻辑要先问这个状态归谁，持有轮次句柄的状态只能由持有者结算；
2. 局限：唤醒后若那一轮的流其实已经断了，界面要等该轮的静默看门狗（最后一个事件之后 3.5 秒）才自愈；一轮若至今没有收到过任何事件，看门狗尚未武装，唤醒不再替它结束 loading，需要用户点停止（按代码阅读，未在真实休眠唤醒里复现）；没有真机休眠唤醒验证。

---

## BUG-AGENT-2026-10-13-006: 点击停止后，工作区流上挂起的读取不会结束，数秒后看门狗清掉下一轮的运行状态；退避等待不响应停止

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P2（停止后立刻发送下一条消息，数秒后下一轮的 `loading` 与 Stop 句柄被上一轮的看门狗清掉：停止按钮消失，服务端继续跑到结束；停止一个正在退避重试的请求，要等睡完整段退避才结束该轮） |
| 影响范围 | `myrm-agent-frontend/src/store/chat/consumeStream.ts`、`streamConsumer.ts`、`src/lib/utils/networkResilience.ts`（新增 `abortableDelay`）、`src/lib/backend-health-probe.ts`（改用 `abortableDelay`） |
| 出现次数 | 1（真实多路复用桥 + 真实 store 管线复现，未取得线上遥测） |
| 关联 | `BUG-AGENT-2026-10-13-001`（回合归属：本条补上其未覆盖的「停止后挂起的读取」）、`BUG-AGENT-2026-10-13-005` |

### 现象

1. 生产默认的传输是工作区多路复用 SSE（`shouldUseMultiplexedAgentStream` 只在直连 E2E 标记下为假）。用户点停止后，桥只摘掉自己的分发处理器（`multiplexChunkBridge.ts:40-50`），合成的 `ReadableStream` 既不关闭也不报错（只有收到终止块后才在 50 ms 后关闭，`:73-83`），`consumeStream` 里挂起的 `reader.read()` 永远不返回；
2. 该轮的静默看门狗（最后一个事件之后 3.5 秒，`streamWatchdog.ts:53`）随后触发自愈，写 `setLoading(false)` 与 `clearActiveStream`；若用户停止后已发出下一轮，被清掉的是下一轮的 `loading` 与 Stop 句柄；
3. 请求重试退避（2 秒起、×1.5、最多 10 次）与断流后的 attach 重连退避是不可中止的睡眠：停止要等睡完才结束该轮；请求重试的睡眠醒来后抛出上一次的网络错误而不是 `AbortError`，用户主动停止被当成网络失败处理；
4. 首次 POST 之前的 multiplex 就绪门（`waitUntilReady(30_000)`）同样不可中止，且返回后不检查中止信号：停止发生在门等待期间、门最长 30 秒后判定失败时，被停止的回合仍按「服务端没有接收该轮」处理，撤回用户气泡并弹发送失败提示；门判定成功时则继续构造请求。

### 根因

1. 取消只做了一半：停止信号只让桥摘掉分发处理器，没有任何东西去唤醒已挂起的 `reader.read()`；读循环此后只能靠静默看门狗兜底，而看门狗收尾写的是共享的回合状态，它不属于已被停止的那一轮；
2. 退避睡眠不接收中止信号，醒来后的 `if (aborted) throw lastError` 抛的是网络错误而不是中止，停止的语义被改写成失败；
3. 就绪门返回后没有检查中止信号：门的判定直接决定回合结局，而停止已经让这一轮没有人再等待。

### 修复

1. `consumeStream`：在中止信号上登记监听，触发时取消 reader（唤醒挂起的读取）；循环顶部、读取失败的 `catch`（在包成 `StreamInterruptedError` 之前）、读取返回之后（在判断 `done` 之前，免得把停止当作流自然结束而走 `onReaderDone` 自愈）各做一次 `throwIfAborted()`，一律以真正的 `AbortError` 结束；监听器在 `finally` 里摘除；
2. 新增 `abortableDelay(ms, signal)`（`networkResilience.ts`；`backend-health-probe.ts` 原来的私有 `sleep` 改用它）：到期 resolve，中止则立即以中止原因 reject，进入时已中止则不启动计时器，计时器与监听器在任何结局后都清理；请求重试退避与 attach 退避改用它，原来「醒来再检查中止」的两处判断随之删除；
3. `sendMessage` 的 catch 本就忽略 `AbortError`（`error instanceof Error && error.name !== 'AbortError'` 分支），被停止的回合因此安静结束：没有失败提示、没有失败标记。页面卸载时 `requestManager.cancelAllRequests` 会以字符串原因中止同一个回合控制器（`requestManager.ts`、`services/chat.ts` 的 `createAISearchStream` 注册），该分支同样不处理非 `Error` 值，所以也是静默的；
4. `executeStreamWithRetry` 在 `waitUntilReady` 返回后立即 `throwIfAborted()`：被停止的回合无论门判定成败都以 `AbortError` 结束，不构造请求、不上报门的判定。门本身仍不可中止（最长 30 秒），界面由 `stopMessage` 当场把 `loading` 置假并清掉句柄，随后到达的收尾由回合归属守卫（`BUG-AGENT-2026-10-13-001`）跳过。

### 验证

1. 红灯先行：把 `networkResilience.ts`、`consumeStream.ts`、`streamConsumer.ts` 还原为修复前（HEAD）源码运行同一批测试，27 例中 13 例红、14 例绿（运行后三个文件逐字节还原）。红的 13 例是：`networkResilience.test.ts` 的 `abortableDelay` 4 例；`streamConsumer.test.ts` 的 7 个停止用例（已停止的回合不开始读取、挂起的读取立即结束且不留下看门狗自愈、读取因停止失败时报告为停止而非断流、监听器随消费结束摘除、不对停止后的流重新 attach、请求重试退避可中止、attach 退避可中止）；`messageRequest.turnOwnership.test.ts` 的 2 例管线用例（停止后等待重试的回合安静结束；停止后的多路复用回合不会留下看门狗去结束下一轮，用真实多路复用桥与真实 store）。修复后全部变绿；
2. 变异检查（A0 基线 13 例通过、0 失败；逐个应用 10 个变异，每次运行后恢复并核对文件哈希）：`abortableDelay` 进入时已中止却不提前拒绝 → 1 红；中止时不清计时器 → 3 红；到期后不摘监听器 → 1 红；中止时不取消 reader → 2 红；读取返回后不检查中止 → 1 红；读取失败的 `catch` 里不检查中止 → 2 红；循环顶部不检查中止 → 1 红；`consumeStream` 的监听器不在 `finally` 摘除 → 1 红；请求重试退避不响应停止 → 2 红；attach 退避不响应停止 → 1 红。其中「读取返回后不检查中止」只被单元用例捕获，管线用例捕获不到（该变异下过期自愈发生在停止当下、下一轮开始之前），由单元用例钉住；
3. 相关 22 个测试文件 253 个用例全绿；oxlint、prettier、窄范围与全量 `tsc --noEmit` 对本修复涉及的文件无问题（全量 `tsc` 只剩他人 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误）；
4. `backend-health-probe.ts` 的私有 `sleep` 本就可中止，改用 `abortableDelay` 只是去重，行为不变，所以不存在红灯用例；`lib/__tests__/backend-health.test.ts` 为此新增 2 个特征化用例（轮询间隔等待期间中止立即返回 false，`waitForTauriRuntime` 与 `waitForBackendReady` 各 1），在修复前的源码上同样通过。把 `abortableDelay` 改成忽略中止信号的变异让这 2 例变红、其余 13 例通过，运行后文件逐字节还原；该文件现 15 例全绿；
5. 就绪门：`streamConsumer.test.ts` 新增 2 个用例（停止之后门判定失败、停止之后门判定成功，各 1）。修复前 2 例都红：门判定失败时回合以 `RequestRefusedError` 结束而不是 `AbortError`；门判定成功时已停止的回合仍调用了 `createMessageRequest`。修复后该文件 27 例全绿，经由真实 `executeStreamWithRetry` 的 `messageRequest.sendFailure` / `turnOwnership` / `queueSemantics` 与 `streamConsumer.transport` 共 47 例保持全绿（门判定失败且未被停止时仍按「服务端没有接收该轮」处理）。

### 踩坑经验

1. 「摘掉监听」不等于「结束读取」：把 `ReadableStream` 交给消费循环的桥，停止时必须有人唤醒挂起的 `read()`（`reader.cancel()`），否则读循环只能靠看门狗兜底，而兜底写的是共享状态；
2. 取消 reader 会让挂起的 `read()` 以「正常结束」返回，读取返回后必须先 `throwIfAborted()` 再看 `done`，否则停止被当作流自然结束而触发自愈；
3. 等待助手里要先登记中止监听再创建计时器：测试里同步触发回调的 `setTimeout` 替身会在登记之前就执行回调；
4. 局限：`waitUntilReady(30_000)`（`streamConsumer.ts`，`ConnectionManager.waitUntilReady` 只收超时、不收中止信号）仍不可中止，停止发生在等待工作区流就绪期间时，该轮的异步函数要等它返回（最长 30 秒）才结束；这段时间界面不受影响（`stopMessage` 当场复位），回合结束时也不会再上报失败（见修复 4）；行为变化：停止一个正在退避重试的请求，不再迟到地给气泡打失败标记并弹提示，而是安静结束，与首包之前停止的终态一致（该消息留在转录里、没有重试按钮）；没有真实浏览器验证，没有线上遥测。

---

## BUG-AGENT-2026-10-13-007: 订阅登录下线后的遗留与周边缺陷：加密凭据无处断开、预检横幅露出原始发行方 ID、设置中心页头副标题写死「中文 / English」

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P2（遗留的订阅令牌继续加密躺在库里且界面没有断开入口；多语言用户在页头和订阅卡片看到不属于自己语言的文案；预检横幅把 `provider_openai` 这类内部标识当名称展示） |
| 影响范围 | server：`app/api/integrations/provider_oauth.py`、`app/services/agent/oauth_refresher.py`、`app/services/integrations/oauth_store.py`、`app/services/integrations/retired_provider_oauth_purge.py`（新增）、`app/core/channel_bridge/config_loader.py`、`app/core/web_push/push_deep_links.py`、`app/server/lifespan.py`、`app/core/infra/health/server_diagnostics.py`（及删除 `anthropic_policy_diagnostic.py`）；frontend：`src/services/provider-oauth.ts`、`ProviderOAuthSection.tsx`、`NoProviderBanner.tsx`、`src/lib/skills/integrationOAuthDisplay.ts`、`SkillRequiredConnectorsPreflightBanner.tsx`、`reauthToasts.ts`、`DataFlowDisclosurePanel.tsx`、六个设置中心组件、六语言 `locales` |
| 出现次数 | 1（读代码与单元测试确认；没有真实订阅账号可做端到端授权） |
| 关联 | `BUG-AGENT-2026-10-13-002`（设置页深链单一真源：本条把 OAuth 重新授权的落点收敛到凭据页）· harness `4d0be96a2`（同一轮排查中发现的多 Key 丢工具绑定，已在 harness 仓库单独修复并记录）· roadmap topic_07 #281 / #236（Claude、ChatGPT、Copilot 订阅登录的合规裁决与重做草案） |

### 现象

1. 进程内的 Claude / ChatGPT / GitHub Copilot 订阅登录按决定整体下线，保留 xAI SuperGrok。下线只删代码不会删数据：这三个发行方（`provider_anthropic`、`provider_openai`、`provider_copilot`）的访问令牌与刷新令牌仍以加密形式留在 `oauthCredentials` 记录里，没有任何代码再读取或刷新它们，界面也不再有断开入口；
2. 技能预检横幅在缺少 OAuth 连接时直接展示服务端返回的发行方标识（`技能名 (provider_openai)`，xAI 显示为小写 `xai`），且 OAuth 缺失与 MCP 缺失两串之间没有分隔符；
3. 六个设置中心（开发者、系统、记忆、工具质量、技能、模型）共 17 处页头副标题是写死在组件里的 `中文 / English` 单串，所有语言的用户都同时看到两种语言，其中模型页中文部分还把 API 密钥写成「API 秘钥」；
4. 模型页订阅卡片的提示与 toast 用 `locale === 'zh' ? … : …` 分支，日、韩、德、繁体中文用户只能看到英文；
5. 德语目录里两条本来就在目录中的副标题（记忆中心「迁移」`settings.memoryCenter.tabDescriptions.migration`、技能「复利」`settings.skills.compounding.subtitle`）一直是英文原文，德语用户在页头看到整句英文。

### 根因

1. 订阅令牌存放在一条加密 blob 里，没有清理遗留发行方的步骤；`oauth_refresher.py` 里 Copilot 的非标刷新、`oauth_store.py` 的 Copilot 基础地址解析、`config_loader.py` 的发行方映射、前端的三个订阅入口与 PKCE 重开页都是这三条登录的专属代码，随登录一起成为死代码；
2. 预检横幅直接渲染服务端返回的发行方标识 `i.issuer`，没有使用已有的 `formatOAuthIssuerLabel`；该函数只做首字母大写，`xai` 只能得到 `Xai`（品牌拼写是 xAI）；`getOAuthIssuerSettingsPath` 还靠 `provider_` 前缀把订阅发行方指向模型页，三条登录下线后这个分支成了死代码；
3. 副标题与卡片文案没有进 `locales`，违反「所有写死文案进 locales、六语言」的项目规范；
4. `verify-i18n.mjs` 校验键对齐、占位符、翻译壳、术语表与双语对照，不会发现「某语言的值与英文逐字相同」；页头守卫测试最初只覆盖搬进目录的 17 条，另外 5 条原有副标题只做了渲染断言，没有逐语言检查内容。

### 修复

1. server：`provider_oauth.py` 收敛为 xAI 门面（`/xai/start`、`/xai/poll` 委托 `xai_oauth.py`，共用 `/status/{provider}`、`/disconnect/{provider}`，以及仅本地模式的测试种子 / 清理端点）；删除 `oauth_refresher.py` 的 Copilot 刷新分支与 `COPILOT_ISSUER`、`oauth_store.py` 的 `extract_copilot_base_url`；`config_loader._PROVIDER_OAUTH_MAP` 只剩 `xai`（`provider_xai` 别名没有任何写入方：xAI 凭据一直写在发行方 `xai` 下）；`push_deep_links.py` 的 OAuth 重新授权统一落到 `/settings/credentials`；删除 Anthropic 订阅策略诊断探针；
2. server：新增 `retired_provider_oauth_purge.py`，启动期在共享行锁内删除三个遗留发行方——没有遗留项时不写回，无法解析的 blob 不覆盖，重复执行结果相同；`lifespan.py` 在数据库就绪后调用，失败只记 warning、不阻塞启动；
3. frontend：`provider-oauth.ts`、`ProviderOAuthSection.tsx`、`NoProviderBanner.tsx` 收敛为 xAI（首启弹窗只剩一个订阅入口）；订阅卡片文案进 `settings.modelService.oauth`（六语言）；
4. frontend：`integrationOAuthDisplay.ts` 的 `formatOAuthIssuerLabel` 增加品牌名表（用 `Map`，以免 `constructor` 这类标识命中原型属性），删除 `getOAuthIssuerSettingsPath` 与 `provider_` 前缀，OAuth 重新授权落点统一为 `SETTINGS_CREDENTIALS_PATH`（`reauthToasts.ts`、`DataFlowDisclosurePanel.tsx`、`getIntegrationSkillSettingsPath` 同步）；预检横幅改用 `formatOAuthIssuerLabel` 渲染并补上两串之间的分隔；
5. frontend：六个中心的 17 条副标题搬进六语言 `locales`（`settings.{developerCenter,systemCenter,memoryCenter,toolQualityCenter,modelCenter}.tabDescriptions.*`、`settings.skills.tabSubtitles.*`），组件改用 `useTranslations`，「API 秘钥」改为「API 密钥」；删除六语言里已退役的 `chat.subscriptionCopilot / Openai / Claude / PkceNotice / PkceReopen` 与 `i18n-shell-allowlist.json` 里对应条目；
6. frontend：页头守卫测试把五个中心的全部标签页副标题（20 条）放进同一张清单，逐语言断言单语言、非英文并渲染；`de.json` 里上述两条译为德语。

### 验证

1. 清理逻辑的变异检查：`test_retired_provider_oauth_purge.py` 7 例在原实现下全绿；逐个应用 4 个变异（用抛弃式 pytest 插件在解释器内改写模块源码，项目文件不动）：遗留列表恒为空 → 3 红；把 `xai` 也列入遗留 → 5 红；去掉「无遗留项不写回」的提前返回 → 2 红（密文变化证明发生了重写，无法解析的 blob 被覆盖）；只写回不删除 → 3 红；锚点不存在时插件直接报错，证明改写确实生效；
2. 前端：对订阅卡片、首启弹窗、预检横幅、发行方展示名、重新授权 toast、数据流披露面板逐个做变异检查（约 25 个，均先红后绿，用抛弃式 vitest 配置，项目文件不动）；副标题新增 `centerSubtitles.test.tsx`：直接读六语言 `locales/*.json`，对 17 条副标题断言单语言（无「中文 / English」混排、英德无 CJK、其余语言含 CJK 且不等于英文），并以真实目录解析（缺失路径即抛错）渲染六个中心的每个标签页、六种语言共 132 例；对它应用 3 个变异（映射到不存在的 key、两个标签文案互换、key 拼错）分别 6、12、6 例变红；
3. server：受影响的两批共 227 个用例通过（`web_push`、设置深链架构测试、`provider_oauth` 接口、`config_loader`、`model_resolver_enrich`、清理逻辑；OAuth 刷新 / 存储 / 会话凭据 / 诊断 / lifespan 等）；其中 `test_oauth_reauth_sse.py` 的 1 例因他人把 `_EVENT_TEMPLATES` 从 `dispatcher.py` 挪到 `adaptive_cards.py` 而早已红，把导入改到新位置后该文件单独复跑 3 例通过；`ruff check`、`ruff format --check` 对触及的服务端文件通过；
4. frontend：11 个相关测试文件 355 例全绿；受影响目录的广域扫描 360 个文件 2215 例中 2213 例通过（见下方局限）；`verify-i18n.mjs`（含全量 key 对齐、占位符、翻译壳、双语对照、纯净门禁）、`prettier --check`、oxlint、`verify:stable-mocks`（本次触及的文件）通过，全量 `tsc --noEmit` 只剩他人 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误；
5. 页头守卫扩到全部 20 条副标题后立即红 2 例（德语两处仍是英文；并行会话的全量 vitest 也报过这 2 例），翻译后 `centerSubtitles.test.tsx` 241 例全绿，`verify-i18n.mjs` 六语言通过；
6. 局限：没有真实订阅账号与真实浏览器，xAI 设备码授权的端到端流程没有重新跑过，只有单元测试与前端交互测试；对 mypy 报告里落在 `oauth_store.py`、`oauth_refresher.py`、`server_diagnostics.py` 的既有报错，确认与本次改动的行不重叠，但没有在 HEAD 基线上单独比对错误数；pyright 在本机解析不到 `sqlalchemy`，结果无效。

### 踩坑经验

1. 删登录只删代码不够：令牌存在加密 blob 里，必须同时有启动期的幂等清理，并且要证明两件事——不会清掉还在用的发行方（`xai`、`google_workspace`），也不会改写没有遗留项的 blob 或覆盖无法解析的 blob（加密每次写入用新的随机数，密文不变即证明没有重写）；
2. 变异检查要覆盖「清得太多」与「写得太多」两个方向，只测「清掉了」会放过把现役发行方也清掉的实现；
3. 前端测试里 mock `next-intl` 的 `t` 必须是稳定引用（`verify:stable-mocks` 会拦），按命名空间缓存同一个函数；
4. 守卫测试的覆盖面要等于被守卫的集合，而不是这次改过的那部分：只逐语言检查搬进目录的 17 条，放过了同一页头里另外两条德语英文值。同类缺口仍在：按「长度大于 25 且含至少 3 个英文单词」的启发式统计，修复前 `de.json` 有 162 条值与 `en.json` 逐字相同（`settings.` 下 62 条），`verify-i18n.mjs` 不会报，未处理；
5. 局限（已核实、未处理，不属于本次范围）：`NoProviderBanner` 的启动授权失败路径先 `setActiveFlow(null)` 再用 `setActiveFlow((prev) => prev ? … : null)` 写错误，错误永远写不进去，用户看不到失败原因；授权轮询返回的 `pollRes.error` 与异常的 `err.message` 会原样展示给用户；预检横幅只缺 MCP 时点击落在 `/settings/skills`，而 `getIntegrationSkillSettingsPath` 对 MCP 给的是 `/settings/agents#loadout`；IM 通知模板 `adaptive_cards.py` 的 OAuth 重新授权文案写「Settings → Integrations」，设置菜单里没有这一项（凭据页叫 Credentials）；`tests/api/integrations/test_mcp_registry_api.py` 有两例依赖线上 Smithery 网络；`MemoryGuardianCard.test.tsx` 的 1 例在受影响目录扫描里失败（单独运行同样失败，渲染停在骨架屏，源文件与测试均未被本次改动）；`BuiltinToolsPanel.kanban.test.tsx` 的 1 例在满载的扫描里超时，单独运行通过。

---

## BUG-AGENT-2026-10-13-008: 重新迁移同名技能时，已有的用量账本被迁移快照整体覆盖（结果、历史、置顶标记丢失）

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-13 |
| 严重程度 | P2（数据丢失：本机已积累的技能结果与使用历史被快照覆盖，无法恢复） |
| 影响范围 | `myrm-agent-server/app/api/skills/migrations.py`, `myrm-agent-server/app/services/migration/skill_bundle_writer.py` |
| 出现次数 | 1（用例复现，未取得线上遥测） |
| 关联 | `BUG-AGENT-2026-10-13-009`（同一批次的技能账本）；提交 `8429cc390` |

### 现象

批准一次 Hermes 技能迁移时，若本机已有同名技能，它的 `.stats.json`（已观测结果、使用历史、置顶标记）被迁移快照整体覆盖。`SKILL.md` 在覆盖前有备份，账本没有。

### 根因

应用步骤对账本无条件写入快照。批量导入「替换同名技能」时会把原账本带过去，迁移路径与之不一致。

### 修复

已有账本永远优先于快照；没有账本的同名技能才用快照播种。应用步骤从 API 层搬到 `services/migration/skill_bundle_writer.py`，`migrations.py` 随之回到文件大小上限内。

### 验证

1. `test_usage_sidecar_import.py` 新增两例：`test_existing_ledger_is_never_replaced`、`test_seeds_ledger_for_existing_skill_without_one`；
2. 本条与下一条涉及的 4 个服务端测试文件共 52 例通过（`test_usage_sidecar_import.py`、`test_usage_sidecar_integration.py`、`test_growth_dashboard_skill_range.py`、`test_skill_growth_outcomes.py`）。

### 踩坑经验

1. 「有备份」只对被备份的那个文件成立：一个目录里并存的旁路文件（账本、置顶标记）要逐个问「覆盖时谁来保」；
2. 同一业务有两条写入路径（批量导入与迁移）时，行为差异本身就是缺陷来源，应收敛到同一个写入器。

---

## BUG-AGENT-2026-10-13-009: 技能趋势与 7 天次数静默少算最旧的运行（账本只留 200 条），趋势面板还不跟随 7/30/90 天范围

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-13 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（看板数字低于真实值且没有任何提示） |
| 影响范围 | `myrm-agent-server/app/api/statistics/skill_growth/{ledger,trends,health,models}.py`, `myrm-agent-frontend/src/components/features/growth/{SkillTrendChart,SkillHealthPanel,growthMarkdownExport}` |
| 出现次数 | 1（用例复现，未取得线上遥测） |
| 关联 | `BUG-AGENT-2026-10-13-008`、`BUG-AGENT-2026-10-14-001`；提交 `4894f5c2c`、`ad38e1be5`、`efdef9e72` |

### 现象

1. 技能趋势面板不理会 7/30/90 天选择器，永远显示整本账本，是看板上唯一不随范围变化的面板；
2. 技能账本只保留最近 200 次运行：一周跑了 336 次的技能，趋势图与健康面板的 7 天次数都显示 200；
3. 范围变化后，所选技能不在新范围内时图表停在最忙技能上，却没有任何标签高亮；空态写「暂无技能使用数据」，对只是这个范围里没有运行的用户是错的。

### 根因

趋势取数不带窗口。账本满（200 条）时分不清「被丢弃的运行」与「本来没有的运行」，计数却被当作总数展示。选择与空态没有处理「范围变了」。

### 修复

趋势窗口随所选范围（滚动 N 天，与健康、成本面板同口径），日按请求方时区划分。序列与健康项带 `truncated`：仅当账本已满且其最早保留的一次运行晚于窗口起点时为真。界面把次数读作下界（`200+`），趋势图说明更早的运行「可能」缺失（账本已满时分不清丢弃与不存在，措辞不下断言）。所选技能不在新范围内时回落到用得最多的技能，始终有一枚高亮标签并带 `aria-pressed`，空态按范围措辞。被丢弃的运行无法找回，没有新增存储。

### 验证

1. `test_skill_growth_outcomes.py`：每天三次、共 100 天的技能，90 天范围被标为截断而 30、7 天完整；一周 336 次的技能读出 `(200, True)`；`test_growth_dashboard_skill_range.py`：所选范围就是趋势窗口、截断标志到达客户端；
2. 服务端相关 4 个测试文件共 52 例通过（与上一条合计）；前端 `SkillTrendChart.test.tsx`、`SkillHealthPanel.test.tsx`、`growthMarkdownExport.test.ts` 覆盖截断说明、选择回落与范围化空态。

### 踩坑经验

1. 容量上限产生的数字是下界，不是总数：凡展示它的地方都要带出「可能不全」，并且措辞与已知信息一致；
2. 面板一旦随范围变化，依赖列表的 UI 状态（当前选择、空态文案）要同时处理「范围变了」。

---

## BUG-AGENT-2026-10-14-001: 技能趋势图一根柱子都不画且横向溢出；健康雷达无描边、黑填充；五环中心刷新按钮写死中文

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（成长看板的两个图表不可用，刷新按钮在英文界面显示中文） |
| 影响范围 | `myrm-agent-frontend/src/components/features/growth/{SkillTrendChart,skillTrendSeries,HealthRadar,LearningLoopFiveRingHub}`，`locales/*.json` 的 `growthDashboard.learningLoop.refresh` |
| 出现次数 | 1（真实组件在 Chrome 中量到，未取得线上遥测） |
| 关联 | `BUG-AGENT-2026-10-13-009` |

### 现象

1. 成长看板（`/journey`）的技能趋势图一根柱子都不画：同一份 30 天数据在真实 Chrome 里量，行高 128px，30 根柱的高度全是 0px；视口 500px 时该行 `scrollWidth` 921、`clientWidth` 442，横向溢出；
2. 代码里 0% 与无数据都按 2% 的短桩画，分不出「全部失败」与「没有观测」；当日值只在鼠标悬停（`group-hover` 与 `title`）时可见，触屏读不到；
3. 概览页的记忆健康雷达没有描边，填充是黑色；
4. 五环中心的「刷新」写死中文，英文界面也显示；五个环卡片是 `div role="button"`，触发 oxlint 的 `jsx-a11y/prefer-tag-over-role`。

### 根因

1. 柱子写成 `height: N%`，百分比相对一个没有高度的 flex 列容器解析，得 0；每列还各带一个悬停数值与一个日期标签，30 列的最小宽度之和（921px）超过容器（442px）。这种写法自 `6010b682c`（2026-07-13）起如此，jsdom 没有版面，单测看不到；
2. 雷达颜色写成 `hsl(var(--primary))`，而主题变量里存的是完整颜色（`globals.css` 的 `--primary: #6799a0`，运行时由 `theme-engine/compiler.ts` 写入同类值），包进 `hsl()` 即无效值：描边 `none`、填充黑；
3. 「刷新」是写死的中文；卡片是带键盘处理的 `div`，不是 `button`。

### 修复

1. 柱区换成仓库统一的 `lazy-recharts`（定高 128px 的 `ResponsiveContainer` + `BarChart`）：定高从结构上排除 0 高度，横轴自动抽稀，悬停与触摸都读出当日值；0% 是红色短柱，无观测的日子留空；成功率纵轴固定 0–100%。逐柱颜色写在数据行的 `fill`，不用 `Cell`；柱色用不透明的 600 色阶（浅色主题下原先的 500 色阶带 0.8 透明度，按 WCAG 公式算与卡片底色的对比度只有 2.1 到 2.95，低于图形元素要求的 3:1；600 色阶不透明时两个主题下都不低于 3.6:1）；`skillTrendSeries.ts` 在技能首末次运行之间补齐没有运行的日子，让横轴是日历；
2. 雷达颜色直接取 `var(--border)`、`var(--muted-foreground)`、`var(--primary)`；
3. 「刷新」走 `growthDashboard.learningLoop.refresh`（六语言）；五个环卡片改为真正的 `button`（原生支持 Enter 与空格，去掉手写的键盘处理）。

### 验证

1. 真实组件在 Chrome 渲染（经 bun 打包真实的 `lazy-recharts`、`next-intl` 与编译后的 `globals.css`；500、800、1280px，浅色与深色）：30 天含 4 个无数据日 → 26 根柱全部可见，最小 3px、最大 94px；90 天 77 根；SVG 宽 442px 等于容器宽度，区块 `scrollWidth` 等于 `clientWidth`（476），无溢出；30 天横轴抽稀为 7 个刻度；悬停读出当日值与已观测次数，无数据日读出破折号；切到次数后（10 日有运行的序列）为 10 根蓝柱；失败日 5 根为红、其余 21 根为绿；
   同一份 30 天数据交给修复前的组件（取自 `HEAD`）：30 根柱高度全为 0px，行 `scrollWidth` 921、`clientWidth` 442；
2. 雷达：描边 `rgb(103, 153, 160)`、网格 `rgb(236, 234, 228)`；修复前量得描边 `none`、填充 `rgb(0, 0, 0)`；
3. 五环卡片：改前（`div`）与改后（`button`）在 500、800、1280px 下盒子与文字位置逐项一致；Enter 与空格都能把看板切到对应页签；
4. 新增 24 例测试：`skillTrendSeries.test.ts` 9、`SkillTrendChart.test.tsx` 12、`HealthRadar.test.tsx` 1、`LearningLoopFiveRingHub.test.tsx` 2。10 个变异（失败色挂错值、次数 0 画成柱、不补空日、逐行 `fill` 丢失、成功率纵轴交给数据、提示对无观测日显示次数、雷达改回 `hsl()`、环卡片跳错页签、刷新改回写死、图表容器高度改回百分比）全部被测试杀死，运行后文件按哈希核对还原；
   最终颜色在 Chrome 中量得：浅色主题 26 根柱为 21 根 `oklch(0.596 0.145 163.225)`（emerald-600）与 5 根 `oklch(0.577 0.245 27.325)`（red-600），深色主题次数柱为 `oklch(0.546 0.245 262.881)`（blue-600）；图表 `svg` 为 `role="application"`、`tabindex="0"`，可用键盘聚焦；
5. `oxlint` 对 growth 目录无输出，`prettier --check` 对触及的代码文件通过，`verify-i18n.mjs` 六语言通过，全量 `tsc --noEmit` 只剩他人 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误。

### 踩坑经验

1. jsdom 没有版面：高度、宽度、溢出类缺陷单测看不到。这类面板要用真实组件在真实浏览器里量一次；并且让图表依赖定高，而不是父级没有的百分比；
2. 原型要走仓库真实的封装：直接用 recharts 时 `Cell` 能给每根柱上色，经 `lazy-recharts` 的包装组件却不被图表库按子类型识别，柱子落回默认黑色，同一份原型在两处结论相反；
3. 主题变量是完整颜色，不要包 `hsl()`。同类写法还在 `KanbanGraphView.tsx`（9 处）与 `SkillQualityTrendChart.tsx`（7 处）；它们用的 `--primary`、`--chart-2`、`--chart-4`、`--destructive`、`--card`、`--border`、`--background` 在 `globals.css` 里都是十六进制，`--success`、`--warning` 在其中没有定义，但两个组件本身没有渲染确认，本次未动；
4. `Cell` 的问题不限于柱图：同一封装下用探针渲染一个 `Pie`，三个 `Cell` 子元素的颜色都被忽略，扇区全是默认的 `rgb(128, 128, 128)`；把颜色写进数据行的 `fill` 后分别为 `rgb(225, 29, 72)`、`rgb(22, 163, 74)`、`rgb(37, 99, 235)`。`EnterpriseUsageTab.tsx:197` 与 `EnterpriseAuditTab.tsx:235` 是同样的写法，组件本身没有渲染，本次未动；
5. 局限：没有在完整 Next 应用里跑过（需要后端数据）；触摸只用合成事件验证了接线；Chrome 最小视口 500px，360px 未实测；真实用户是否受影响没有线上遥测。

---

## BUG-AGENT-2026-10-14-002: 24 处把主题变量包进 hsl()/rgb() 导致描边、填充、阴影、高亮静默失效；懒加载图表包装吞掉 Cell 的逐项颜色

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（看板依赖连线与小地图、技能质量趋势线、小时分布图看不见或颜色错，企业用量 / 审计饼图按探针推断颜色错；不丢数据） |
| 影响范围 | `myrm-agent-frontend/src/components/features/{kanban/KanbanGraphView,settings/sections/ai-tools/SkillQualityTrendChart,settings/sections/system/UsageDistributionCharts,memory/command-center/MemoryCommandCenterPanels,app-shell/lazy-recharts}`，`components/approval/HighRiskEvidenceScreenshot`，`components/auth/LocalLoginForm`，`src/app/globals.css`，新增门禁 `scripts/{check-theme-colors.mjs,theme-color-scan.ts}` |
| 出现次数 | 1（真实组件在 Chrome 中量到，未取得线上遥测） |
| 关联 | `BUG-AGENT-2026-10-14-001`（同一类写法，当时只修了成长看板） |

### 现象

1. 任务看板的依赖图：父任务为已完成、已阻塞、已失败的连线整条看不见；小地图上已完成与已阻塞的任务点是黑色（深色主题下是一块黑方块）；
2. 设置里的技能质量趋势：折线与参考线不显示（浅色主题只剩坐标轴，深色主题只剩数据点）；
3. 设置里的小时活动分布：折线无描边，渐变填充是黑色，深色主题下几乎看不到；
4. 企业用量 / 审计的饼图（`EnterpriseUsageTab.tsx:197`、`EnterpriseAuditTab.tsx:235`）：按同一封装的探针渲染，所有扇区是同一个灰色，而用量页旁边的图例色块是彩色，对不上（这两个页面本身没有渲染，需要后端数据）；
5. 记忆中心的呼吸光点、高危操作截图的红圈光晕、本机登录输入框的聚焦光环都没有阴影；`<mark>` 高亮没有底色；
6. 设置里的技能质量趋势在英文等非中文界面上，横轴与演化标记的日期仍是「10月1日」这种中文格式；同一组件里还有 16 处 `t('…') || '写死的文案'` 兜底（15 处中文、1 处英文）。

### 根因

1. 这些位置写的是 `hsl(var(--primary))`、`rgba(var(--primary),0.1)` 之类。主题变量里存的是完整颜色（`globals.css` 的 `--primary: #6799a0`，`theme-engine` 只接受 `#RRGGBB` 并以同样的值写入运行时），包进 `hsl()` 在计算期是无效值：Chrome 中量到内联 SVG 的 `stroke` 为 `none`（并盖掉 class 里的描边）、`stop-color` 为 `rgb(0, 0, 0)`、`box-shadow` 为 `none`、`mark` 背景透明。这是把「变量只存三个通道数」的旧写法抄进了存完整颜色的主题里；
2. 看板与质量趋势里用的 `--success`、`--warning` 在 `globals.css` 中没有定义，深色主题的 `--destructive` 是 `#801d1d`（太暗），浅色主题的 `--chart-2` 是 `#4add80`（落在卡片底色上对比度约 1.7），直接换成 `var()` 仍不可读；
3. 日期用写死的 `'zh-CN'` 格式化，不跟随界面语言；文案兜底是遗留的写死文本，而 `settings.skillAggregation` 下这些键在六种语言里都有，兜底是死代码；
4. 饼图的颜色写在 `Cell` 子元素上，而 recharts 按 `type.displayName || type.name` 识别 `Cell`（`Pie` 与 `Bar` 都是），`lazy-recharts` 用 `next/dynamic` 生成的包装组件叫 `LoadableComponent`，于是所有 `Cell` 被忽略：扇区是 `rgb(128, 128, 128)`、柱子是黑色。

### 修复

1. 22 处业务代码按用途改写：主色用 `var(--primary)`；半透明用 `color-mix(in srgb, var(--primary) 20%, transparent)`（仓库已有 97 处同类写法），Tailwind 类里用 `shadow-[0_0_8px] shadow-primary/55` 这样的透明度修饰符；
2. 成功与警告没有主题变量，取 Tailwind 色阶并带回退 `var(--color-emerald-600, #059669)`、`var(--color-amber-600, #d97706)`（Tailwind v4 只为用到的工具类输出 `--color-*`，回退值保证没被引用时也有色）；失败 / 阻塞用 `var(--color-red-600, #dc2626)`，不用深色主题下太暗的 `--destructive`；
3. `lazy-recharts` 工厂给每个包装组件设置 `displayName = <recharts 导出名>`，与未包装时一致；
4. `globals.css` 的 `mark` 两条规则改为 `color-mix`，并删除无任何引用的遗留类 `.input-default-theme--ujGK4`（其 `rgba(var(--primary))` 同属此类）；
5. 新增门禁 `bun run verify:theme-colors`（已接入 `bun run lint`，即 CI `frontend-build.yml`）：`src/` 下 ts / tsx / css 出现「变量即整个颜色」的 `hsl|hsla|rgb|rgba(var(--x) …)` 即失败，测试文件不扫描；变量作色相通道（`hsl(var(--agent-hue) 58% 48%)`）、`--widget-*`（iframe 内注入三元组，`widget-theme-bridge.ts` 两处）为合法写法，不拦。
6. 门禁增加前提自检：`globals.css` 的 `--primary` 不是完整颜色（例如改成 `210 40% 50%` 通道三元组）时直接失败，而不是继续拦合法写法；`isCompleteColorValue` 配 2 例单测；
7. 技能质量趋势的日期改用界面语言（`useLocale()`），数据点与演化标记共用同一个 `formatTrendDate`（图表按这个字符串对位，两处必须一致）；删除 16 处写死兜底；新增组件测试 5 例；
8. `ChatWindowAgentFromUrl.test.tsx`（`HEAD` 已提交）的 `next-intl` mock 每次渲染新建函数，使 `verify:stable-mocks` 在 `HEAD` 上就失败；`lint` 链用 `&&` 串联，新门禁根本到不了。改为模块级稳定引用。

### 验证

1. 真实组件在 Chrome 渲染（经 bun 打包真实的 `KanbanGraphView`、`HourDistributionChart`、`SkillQualityTrendChart`、`lazy-recharts` 与由真实 `globals.css` 编译的 Tailwind；视口 960×700，浅色与深色）：
   - 看板连线：已完成 `oklch(0.596 0.145 163.225)`（emerald-600）；阻塞 / 失败 `oklch(0.577 0.245 27.325)`（red-600）且为 `5px, 3px` 虚线；默认连线不变。小地图点：已完成 emerald、阻塞 / 失败 red、就绪 `rgb(103, 153, 160)`（浅）/ `rgb(107, 163, 170)`（深），遮罩为带 0.7 透明度的背景色；
   - 小时分布：描边与渐变两个 `stop-color` 都是 `--primary`（浅 `rgb(103, 153, 160)`，深 `rgb(107, 163, 170)`）；
   - 技能质量：质量线 `--primary`、成功率线 emerald-600，浅色与深色都可见；
   - 饼图（经 `lazy-recharts`）：三个扇区 `#e11d48`、`#2563eb`、`#059669`；
   - 阴影按源码里的原样类名量：光点 `oklab(… / 0.55) 0 0 8px`，红圈光晕 `oklab(… / 0.15) 0 0 0 5px`，登录聚焦光环 `oklab(… / 0.1) 0 0 0 4px`，深色主题同样成立；`mark` 背景浅 `color(srgb 0.404 0.6 0.627 / 0.2)`、深 `… / 0.3`；
   - 修复前（同一批真实代码取自 `HEAD`）：连线 `stroke: none`、小地图点黑色、质量线与小时折线无描边、渐变 `rgb(0, 0, 0)`、阴影 `none`、`mark` 透明、饼图扇区 `rgb(128, 128, 128)`；
2. `lazy-recharts` 契约测试 2 例（真实 `PieChart` / `BarChart`，不 mock）：把 `displayName` 那一行删掉后两例都失败（扇区三个 `#808080`、柱子三个 `null`），恢复后通过；
3. 门禁：对 `HEAD` 上的原文件运行扫描，恰好命中原来的 25 处（看板 9、质量趋势 7、用量分布 3、记忆 1、高危 1、登录 1、`globals.css` 3），`widget-theme-bridge.ts` 为 0；往 `src/` 临时放一个含 `hsl(var(--primary))` 与 Tailwind 任意值 `_hsl(var(--primary)/0.55)` 的文件，门禁退出码 1 并指出行号，删除后退出码 0；单测 6 例；
4. 对比度按 WCAG 公式算（未在浏览器中量）：emerald-600 在浅 / 深色卡片上 3.63 / 5.25，amber-600 为 3.07 / 6.21，red-600 为 4.66 / 4.10，均不低于图形元素要求的 3:1；
5. 技能质量趋势组件测试 5 例（设置里首次有测试）：把 `toLocaleDateString(locale, …)` 改回 `'zh-CN'` 后「按界面语言」一例失败（得到 `10月12日` 而非 `Oct 12`），恢复后通过；真实组件在 Chrome 英文界面的横轴为 `Sep 30`、`Oct 1`，不含中文；门禁的前提自检在隔离副本里验证：`--primary` 改成 `210 40% 50%` 时退出码 1、恢复后 0；
6. `vitest` 触及目录共 109 个文件、822 例通过；`oxlint` 无新增（`HighRiskEvidenceScreenshot` 的 `no-img-element`、`KanbanGraphView` 的 `prefer-tag-over-role` 是原有告警，未动）；`prettier --check` 对本次新增与改动的行通过；全量 `tsc --noEmit` 只剩他人 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误。

### 踩坑经验

1. 主题变量存的是完整颜色，不要包 `hsl()` / `rgb()`：无效值不会报错，只会让整条声明静默落空，jsdom 与单测看不到；
2. 写静态扫描时别用 `\b` 匹配函数名：Tailwind 任意值里 `_` 就是空格，`8px_hsl(` 中的 `_` 是单词字符，`\b` 不成立，最初的版本因此漏掉三处 Tailwind 写法，是靠对 `HEAD` 原文件的扫描结果与人工清单比对才发现的；
3. 经 `next/dynamic` 包装的组件要自己带上 `displayName`：图表库按类型名识别数据型子元素，匿名包装会让它们被悄悄忽略；
4. 局限：没有在完整 Next 应用里跑过（需要后端数据）；技能质量用的是模拟接口数据，其中没有「Token 效率」一条线，琥珀色那一处只验证了回退值能解析（`oklch(0.666 0.179 58.318)`）；只在 Chrome 中量过，Safari / Tauri WebView 未实测；自定义主题下的对比度未计算；`HEAD` 上 `bun run lint` 原本就停在 `verify:stable-mocks`（已修，见修复 8）；当前工作区里他人未提交的 31 个测试仍会触发同一门禁，另有他人未提交的 9 个文件触发键盘焦点硬门禁，`bun run lint` 在这个工作区里到不了新门禁，新门禁可用 `bun run verify:theme-colors` 单独运行；`SkillQualityTrendChart` 里的时间范围显示 `{N}d` 仍是写死的缩写；`globals.css` 里还有若干无引用的遗留哈希类（`.input-size-default--_K_0f`、`.text-ellipsis--D6tEl`、`.search-input--oNVDM`、`.monica-input` 等），不属于本次问题，未动。

---

## BUG-AGENT-2026-10-14-003: 「技能质量」仪表盘整条链路没有数据来源，页面形同虚设；`enable_auto_optimization` 配置项从未被读取

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（死代码 + 误导性开关，无数据损坏） |
| 影响范围 | 前端 `settings/sections/ai-tools/`（5 个组件）、`settingsRoutes.ts` / `SettingsMenu.tsx` / `SettingsLayout.tsx`、六种语言 locale；服务端 `app/api/skills/quality.py`、`app/api/skill_optimization/routes/dashboard.py`、`app/services/skill_optimization/{telemetry_pusher,bootstrap}.py`、`app/adapters/skill_optimization/`、`app/schemas/control_plane.py`、`app/config/settings.py`；plane `telemetry/multi_tenant/`；harness `optimization/{config,scheduler_monitoring_mixin}.py` |
| 出现次数 | 1 |
| 关联 roadmap | 无 |

### 现象

1. 设置 → AI 工具里的「技能质量」「工具质量中心」页面读取 `/skill-quality/*` 与 `/skill-optimization/{dashboard,quality,quality-history,global-metrics,aggregate-by-skill}`，默认部署下没有任何数据写入这些接口背后的存储；
2. 服务端 `TelemetryPusher` 与 plane 的 `MultiTenantAggregator` 都没有被启动 / 实例化，plane 的 `/telemetry/skill-quality` 只有 `logger.debug`；
3. harness 的 `OptimizationConfig.enable_auto_optimization` 没有任何读取点，设为 `False` 也照样每小时评估并自动入队优化；`enable_user_feedback` 同样无人读取。

### 根因

1. 质量快照的写入方 `save_quality_snapshot` 在生产代码里没有调用者；每小时的 `_evaluate_all_skills` 算出分数后直接丢弃，`OptimizationScheduler` 也拿不到存储句柄；默认存储是 `memory`（`settings.py:636-640`）；综合分在生产中是 `0.35 + 0.3*成功率 + 0.2*时间效率`，五个维度里三个是常量；
2. 前端导出按钮调用的路由在服务端不存在；每技能的成功率 / 次数趋势在成长仪表盘（`fetch_skill_trends`，`/journey`）里已有，且来自账本，是活数据；
3. 配置项当年随调度器一起写入，没有接线，也没有测试覆盖，所以一直没人发现。

### 修复

1. 前端：删除 `ToolQualitySection`、`SkillQualitySection`、`GlobalSkillQualityDashboard`、`SkillQualityTrendChart`、`QualityDistributionChart` 及趋势图测试，去掉 `skillQuality` / `toolQuality` 标签、重定向与子菜单（`toolStability` 直接指向 `ToolStabilitySection`），六种语言各删 6 个无引用键；
2. 服务端：删除 `quality.py`（6 个路由）、`dashboard.py`（5 个路由）、无消费者的 `sql_data_source.py` / `heavy_analytics_repo.py`、`telemetry_pusher.py`、`SkillQualityTelemetry` / `TelemetryPushPayload`、`TELEMETRY_PUSH_INTERVAL`、聚合器注册与依赖、没有任何发送方的 `SKILL_QUALITY_UPDATED` 事件（前端透传白名单同步删除），以及对应测试与 `_ARCH.md` 行；
3. plane：删除从未实例化、无测试的 `telemetry/multi_tenant/`（479 行）及其再导出；
4. harness：`_evaluate_all_skills` 在 `enable_auto_optimization=False` 时直接返回（只管定时评估，手动 / 批量触发不受影响；默认 `True`，行为不变），新增 2 例单测；删除从未读取的 `enable_user_feedback`；更正 `optimization/__init__.py`、`protocols.py` 里已不存在的业务层适配器与前端区块的描述；
5. 文档：`myrm-docs` 的 `skill-evolution.mdx` 去掉两行并把「6 面板」改为「4 面板」（en / zh / ko），`error-recovery.mdx` 删除「质量告警 Webhook」一条（`AlertIntegration` 只在 harness 导出，服务端没有任何接线与配置，产品并不具备该能力）。

保留不动：harness 的分析模块（`aggregation_*`、`anomaly_detector`、`predictive_analyzer`，公开 API 且各有测试）、存储协议实现与 `skill_quality_history` 表、成长仪表盘、plane 的 `/telemetry/skill-quality` 与 `/baselines/*` 占位路由。

### 验证

1. 前端：`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx` 一处；`oxlint` 对改动的 4 个文件无告警；`vitest` 设置目录 136 个文件 1039 例中 2 例失败（`centerSubtitles` 的德语目录里两处仍是英文，与本次无关）；`verify-i18n` 与 `verify:theme-colors` 通过；`verify:stable-mocks` / `verify:a11y` / `verify:orphans` 的失败项都在他人文件里，没有一项落在本次改动或被本次删除所孤立的模块上；
2. 服务端：把 `api_router` 挂到空 `FastAPI` 后取 OpenAPI 路径共 2560 条，已不含 `/skill-quality/*` 与上述 5 个 dashboard 路径，其余 `/skill-optimization/*` 保留；受影响目录 pytest 2152 通过、9 失败，9 例都是架构门禁，原因是他人未提交的目录与导入（api/services 同名域 `git`、`machines`、`runs`、`workflow`；`services/workflow` 缺 `__init__.py`；`/memory/simulate-recall` 无前端调用；harness 深导入基线新增 75 条），过期基线条目为 0，即本次删除没有留下陈旧基线；
3. harness：`tests/agent/skills/optimization` 168 例通过（含新增 2 例），`ruff` 无告警；
4. plane：架构与单元测试中与遥测 / 导入相关的 220 例通过；
5. 全仓对已删符号与路由的 `rg` 只剩 `BUGFIX_LOG.md` 里的历史记录与 harness 公开框架 API 本身。

### 踩坑经验

1. 页面存在不等于有数据：先查谁写入，再决定要不要给它做界面；这条链路从写入端到展示端都没接上，却在四个仓里各留了一段；
2. 配置项必须有读取点：没有读取点的开关比没有开关更糟，用户会以为关掉了；
3. 局限：没有核对线上数据库里 `skill_quality_history` 表的实际行数，也不知道外部部署是否设置过存储相关环境变量；未在 Tauri / 移动端实测；未跑 `next build`；旧的 `/settings/toolQuality` 深链现在的落点没有实测。

---

## BUG-AGENT-2026-10-14-004: 技能自动优化链路只有消耗没有产出，批量优化页与「优化前」徽章从未有数据；存储工厂在默认配置下返回没有会话的内存实现

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（死代码 + 后台 LLM 开销，外加一处会让服务启动失败的隐患） |
| 影响范围 | 服务端 `app/{api,services,adapters,database/models}/skill_optimization/`、`app/api/batch_optimization/`、`app/api/skills/evolution/history.py`、`app/server/lifespan.py`、`app/core/infra/server_globals.py`、`app/core/utils/lock.py`；前端 `batch-optimization` / `skill-optimization` 页面、`useBatchWebSocket`、历史面板徽章、六种语言 locale；harness `skills/optimization/ab_test.py`、`config.py`；plane `api/routers/telemetry.py`；`myrm-docs` 六个 `skill-evolution.mdx` |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-14-003`（同一条链路的另一半：当时「保留不动」的 plane 占位路由与调度器这次一并删除） |

### 现象

1. 服务启动时创建 `OptimizationScheduler` 并开始定时评估、批量优化，产出的优化结果没有任何地方保存或应用；
2. 设置里没有入口的「批量优化」页（`/batch-optimization`）、WebSocket 进度、手动 optimize / feedback / health / metrics 路由，以及一个调用不存在的 `/comparison` 路由的 `/skill-optimization` 页，都读不到真实数据；
3. 进化历史里的「优化前」徽章从未出现过：`save_quality_snapshot` 在生产代码里没有调用者，`get_latest_quality` 永远返回空；
4. harness 的 `ab_test.py` 里提前停止、快速失败、选胜者的决策代码没有调用方，`ABTestConfig` 七个旋钮里六个只被这些代码读取；
5. plane 的 `/telemetry/skill-quality` 只写 debug 日志，`/baselines/skills|strategies` 返回占位数据。

### 根因

1. 调度链的采样端没有接线：`ServerSkillExecutionProvider` 的样本方法返回空，质量分算完直接丢弃，批量任务的结果也没有落到任何审批或写盘路径；
2. 设置项 `skill_optimization_storage_type` 默认值是 `memory`，`get_skill_optimization_storage()` 因此返回没有 `_get_session` 的内存存储，依赖会话的路径（批次撤销快照写入）在默认配置下拿到的是错的实现；
3. 这几段是不同时期各写了一半，没有一处是从「谁产出数据、谁消费」倒推出来的。

### 修复

1. 服务端：删除调度器工厂与访问器、批量路由与 WebSocket、手动优化 / 反馈 / 健康 / 指标路由、通知 / 合并 / 提取 / 报告服务、批量任务与审计的仓库和模型、`server_globals`、只被调度器用的 `lock.py`、`SkillBaseline` / `BaselinesResponse` 两个只被基线同步器用的模型；`get_skill_optimization_storage()` 始终返回绑定当前会话工厂的 `SQLAlchemyStorage`，并删除 `skill_optimization_storage_type` 设置；`RollbackService` 只保留技能修改批次撤销要用的快照写入；历史接口去掉 `quality_delta`；
2. 前端：删除批量优化页面、lib、WebSocket hook 与测试，孤儿 `/skill-optimization` 页，「优化前」徽章及六种语言文案，路由白名单与翻译补丁里只为它们存在的条目；
3. harness：`ab_test.py` 只留 `start_ab_test` 与样本量计算，`ABTestConfig` 只留 `min_sample_size`、`max_sample_size`、`enable_adaptive_sampling`；
4. plane：删除 `/telemetry/skill-quality`、`/baselines/*` 及只被它们用的 schema；
5. 文档：`myrm-docs` 的 `core-concepts` 与 `guides` 下六个 `skill-evolution.mdx` 去掉批量优化流程、取消并回滚的「实测」段、质量增量徽章；roadmap `topic_08` 里「server 已接入 lifespan」的前提改正；
6. 启动标签：调度器的初始化任务删除后，`lifespan.py` 里与结果按严格模式 `zip` 的 `_labels` 也要删对应一项，否则两边数量不等，服务启动会抛 `ValueError`；新增 `tests/server/test_lifespan_startup_labels.py` 把两个列表的长度钉在一起。

保留不动：harness 的优化环库（当时未核实可达性，不可达部分已在 `BUG-AGENT-2026-10-14-005` 删除）、`batch_snapshots` 表及其写入（skill_manage 批次撤销在用）、`/skill-optimization/mutations/{id}/rollback`、版本历史与回滚、Shadow A/B、晋升门禁、进化审核、`SkillHealthEvaluator`、`skill_quality_history` 等数据库表。

### 验证

1. 路由：把提交前后的服务端分别导出（同一份已提交的 harness），挂 `api_router` 取 OpenAPI，路径从 1532 条变为 1522 条，少的正是 `GET/POST /batch-optimization/tasks*` 共 6 条与 `GET /skill-optimization/health`、`GET /skill-optimization/metrics`、`POST /skill-optimization/feedback/{skill_id}`、`POST /skill-optimization/optimize/{skill_id}` 共 4 条，新增为 0；
2. 服务端（工作区）：技能 / 优化 / API / 服务 / 架构等目录 pytest 2931 通过、23 失败；失败都落在他人未提交的改动上（curator 与 prebuilt 技能、路由消费者与同名域、`app` 包缺 `__init__.py`、前端 API 路径、harness 深导入、`auto_backup` 告警识别用例在整组运行时失败——单独成因未核实）；`server_harness_import_baseline` 里已过期的条目为 0，即本次删除没有留下陈旧基线；
3. 服务端（已提交内容的干净导出）：`tests/server`、`tests/services/skill_optimization`、`tests/api/skill_optimization`、`tests/services/skills`、`tests/architecture` 共 1933 通过、22 失败；失败里 harness 深导入 2 例与前端 memory 路由 1 例来自他人提交，其余是裁剪导出缺 `scripts/`、安装脚本等文件造成（channel catalog 两例没有逐一核对）；
4. 导入解析：对提交前后的 `app/`、`tests/` 做 AST 导入与 patch 目标检查，两次结果逐行相同，没有新增悬空导入；`git grep` 已删符号与路由只剩本文件的历史记录；
5. 前端：`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx` 一处；`oxlint` 对改动文件无告警；受影响的四个目录 vitest 214 例里 12 例失败，全在 `SkillGrowthCaseCard*` 与 `EvolutionRejectionDashboard.sse` 这些没改过的文件里（`t.has is not a function` 与 SSE 重取次数）；`verify:i18n` 的 219 条缺失键没有一条属于本次删除的键或文件；`verify:orphans` 的清单里没有因本次删除而孤立的模块；`theme-init-asset` 白名单测试通过；
6. harness：`tests/agent/skills/optimization` 工作区 168 例、已提交内容的干净导出 166 例全部通过，`ruff` 无告警；
7. plane：`test_telemetry_routes.py` 与 `test_internal_api_auth_flow.py` 共 45 例，工作区与干净导出都通过，`ruff` 无告警。

### 踩坑经验

1. 删除一个启动任务时，要顺着 `gather` 的结果找所有按位置配对的东西（这里是严格 `zip` 的标签表）；这一处没有被任何现有测试覆盖，是复查 diff 时才发现的，已加测试；
2. 和别人共享工作区时，一个文件里常常混着别人的改动；提交时从 HEAD 文本出发只做自己的修改，比挑 hunk 更稳（相邻改动会被合并成一个 hunk）；
3. 根仓库有 pre-commit 钩子，提交期间会把未暂存的改动整体暂存再恢复，几秒内工作区会被临时改写；
4. 局限：服务启动只在临时数据目录里用真实 lifespan 进入并退出过一次（476 条日志、0 条 ERROR），没有跑过长时间运行；没有核实外部是否有程序抓取 `/skill-optimization/metrics`；进化审核链每个节点的 token 开销没有实测；`batch_snapshots` 表里历史行没有清理；未在 Tauri / 移动端实测。

---

## BUG-AGENT-2026-10-14-005: 技能优化库里 24 个模块没有任何调用方，回滚接口返回自造的审计日志并向无人订阅的事件中心发消息

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P3（死代码与对外误导：公开配置 `enable_auto_optimization` 不起作用，回滚响应带着伪造字段，材料里宣称的能力不存在） |
| 影响范围 | harness `agent/skills/optimization/`（模块、协议、类型、配置、测试、`_ARCH`、行数基线）；服务端 `app/adapters/skill_optimization/`、`app/api/skill_optimization/routes/versions.py`、`app/database/migrations.py`；根仓库四篇优势材料 |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-14-004`（那次对 harness 优化库「保留不动」，这次核实可达性后删除不可达部分） |

### 现象

1. harness 优化包里的调度器、批量执行器、聚合栈、异常与预测分析、死信队列、限流、Prometheus 导出、成本计算、健康检查协议，没有任何生产代码导入；服务端调度器在 004 删除后，它们成了只被自己的测试引用的孤岛；
2. `OptimizationConfig.enable_auto_optimization` 与 `MonitoringConfig` 的旋钮没有读取者；
3. `SkillOptimizationStorage` 协议里 7 个方法（历史、最近优化、清理、A/B 状态更新、样本递增、最好 / 最差技能）没有调用方，服务端存储、三个仓库各为它们写了一份实现，仓库测试里还有对应用例；
4. `POST /skill-optimization/rollback/{skill_id}` 的响应里 `audit_log` 是现场拼的字典（`triggered_by` 写死 `manual`，没有落库），同时向没有订阅者的 `EventEmitter` 发 `version_rollback`；版本对比与详情接口各自手写一份质量分字典，把「没有真实样本」的 0.5 占位分当成真实评分返回，对比出恒为 0 的假增量；
5. `batch_audit_logs`、`batch_optimization_tasks` 两张表在 004 里连同模型失去了读写者，却仍留在已有数据库里；
6. 优势材料里还写着已经删除的批量优化页、质量增量徽章、调度器、异常检测与预测能力。

### 根因

1. 004 删除了服务端调度链和 `ab_test.py` 里的决策代码，没有对库里其余模块逐个核查「谁在导入」，它们仍按「公开 API」被保留；
2. 回滚接口是按设想写的（审计、事件通知），没有对应的存储或订阅端；对比与详情接口复制了一份已有的序列化函数；
3. 这些部分都是为将来的闭环预写的，与实际接上的 Shadow A/B 链没有对账。

### 修复

1. harness：删除 24 个无人导入的模块与只测它们的 14 个测试文件；`SkillOptimizationStorage` 去掉上述 7 个方法，`SkillQualityAggregator` / `SkillQualityDataSource` 协议、`StorageConnectionError` / `StorageTimeoutError` 与聚合 / 预测 / 异常数据类一并删除；`OptimizationConfig` 去掉 `MonitoringConfig`、`enable_auto_optimization` 与三个预设，`PerformanceConfig` 只留优化器读取的 LLM 调用字段；`SkillQualityScore` 去掉再没有人写入的四个成本字段（`prompt_tokens`、`completion_tokens`、`total_tokens`、`llm_cost_usd`），`__init__` 里的 `SkillExecutionSample` 改从定义处导出；包文档、`__init__` 导出、`_ARCH`、mixin MRO 架构测试与行数基线同步收缩；
2. 服务端：存储与三个仓库删除对应的 7 个包装方法及其测试；快照仓库不再读写那四个成本字段（已有行里多出的键读取时忽略），四个仓库的 `desc(列)` 改为 `列.desc()`，消除 8 条 pyright 报错；`versions.py` 的对比 / 详情复用 `_quality_score_payload`（占位分返回 `null`，增量只在两边都有真实评分时计算），回滚接口去掉伪造的 `audit_log`、无人订阅的事件发射和用不到的数据库依赖；
3. 迁移：在 `MIGRATION_STATEMENTS` 末尾追加 `DROP TABLE IF EXISTS` 两条，新增 `tests/database/test_batch_optimization_tables_retired.py`；
4. 文档：`app/adapters/_ARCH.md` 去掉默认内存存储的图示行；plane `api/schemas/_ARCH.md` 去掉已不存在的 Skill baseline 行；根仓库四篇优势材料（提交 `a65d6a5033`）里改成代码事实，另有 `HARNESS_ARCHITECTURE_ADVANTAGE`、`SKILL_MARKET_AND_ADOPTION_ADVANTAGE` 与 roadmap `topic_14` 里对已删模块、已删 A/B 决策代码的引用改成现状，「止损三绳」改为「两绳」，批量执行器测试数 105 改为 97，子智能体总数 500 改为 485。

保留不动：`optimizer.py`、`observability.py`（两者同样没有包外调用方，但带着他人未提交的改动，这次没有碰）；Shadow A/B、晋升门禁、进化审核、`RollbackService` 的批次快照与 `/mutations/{id}/rollback`、`SkillHealthEvaluator`、质量快照三件套与优化记录两件套。

### 验证

1. 可达性：从 `__init__` 再导出和服务端导入出发做包内可达性分析，24 个模块不可达；可达的是 `ab_test`、`config`、`event_adapter`、`event_emitter`、`protocols`、`quality_calculator`、`result_comparator`、`security`、`types`；删除后用已提交内容的干净导出导入整个包与 `skills.evolution`，成功；
2. harness：已提交内容的干净导出里 `tests/agent/skills/optimization` 加 `test_mixin_mro.py` 共 55 例通过（工作区 57 例，多出的 2 例属于他人未提交的 `test_event_adapter.py`）；`ruff check` 与 `format --check` 对改动文件无告警；`tests/architecture` 加 `tests/agent/skills` 整组 10031 通过、16 失败，失败全在他人的改动上（device_mesh 工具注册、curator 与 promotion_gate 的 `_ARCH` 清单、core-IP 清单、行数基线里他人文件、wiki 文档链接、PyPI / wheel 环境检查），没有一条指向 optimization 包；`_ARCH` 清单校验对 optimization 目录为 OK（12 个 py 文件）；
3. 服务端：`SkillOptimizationStorage` 的方法集与 `SQLAlchemyStorage` 的公有方法集逐项对比，两个方向的差集都是 0；`tests/services/skill_optimization`、`tests/architecture`、`tests/api/skill_optimization`、`tests/adapters`、`tests/database` 共 2244 通过、13 失败，失败集中在路由调用方基线（含他人新增的 `package-revisions` 路由）、API / 服务同名域划分、`app` 包布局、前端 API 路径、server 到 harness 的深导入基线，均不涉及本次删除的符号；
4. 迁移：新增表退役测试与 schema 门禁共 8 例通过；回滚 / 版本对比 / 详情路由新增 `test_versions_routes.py`，加质量仓库测试共 12 例通过；
5. 前端：`services/skill/optimization.ts` 的对比 / 详情 / 回滚类型里没有 `audit_log` 与 `score_delta`，`quality_score` 本就允许 `null`，前端不需要改。

### 踩坑经验

1. 可达性分析要把 `__init__` 的再导出算进去：第一版脚本漏了这一步，把仍在被导出的 `ab_test` 判成不可达；
2. 收缩协议要同时收缩实现与测试：协议删掉 7 个方法后，服务端的包装、仓库方法和用例都成了死代码；收尾用「协议方法集与实现方法集的差集」检查；
3. `MIGRATION_STATEMENTS` 的版本号是列表下标，`schema_gate` 用 `len - 1`，所以 DROP 只能追加在末尾；
4. 共享工作区里，同一个 hunk 常常混着别人的相邻行（行数基线、`_ARCH` 表）：提交时把别人的 `+` 行改回 HEAD 文本，或从 HEAD 文本出发重建整份文件，而不是直接挑 hunk；
5. 为迁移写夹具要按旧模型的真实表结构写：旧模型已被删除，从历史提交里取；第一版夹具凭印象给两张表之间写了外键，实际没有；
6. 删掉一个生产者（这里是成本计算器）后，要顺着它写入的字段找「再没人写」的残留；四个成本字段是靠检索字段名找出来的；
7. 局限：`SKILL_EVOLUTION_ADVANTAGE` 里带日期的测试验证表（2026-06-28、2026-07-08）仍记着 optimization 目录 164 例，它们是当时的实测记录，没有改；`topic_11`、`topic_14` 里仍在他人工作区、尚未提交的条目，工作区文本改了，没有提交；`dependencies.py` 里 `get_event_emitter` 的删除依赖他人未提交的 `runtime.py`，留在工作区没有提交；`optimizer.py` / `observability.py` 的去留需要在他们的改动落地后再核实；没有重新跑服务启动的完整流程，也没有实测前端页面。

---

## BUG-AGENT-2026-10-14-006: 平板与横屏手机上看不到用户消息的动作行（含 Rewind 唯一入口）；41 个组件的 46 个功能控件只靠悬停或宽度断点显现，键盘够不到；TSX 硬编码文案没有门禁

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（功能性控件在无悬停设备上不可达，键盘也无法触达；不影响数据） |
| 影响范围 | 前端 `lib/utils/a11y.ts`、43 个组件文件（`message-box`、`artifacts`、`kanban`、`settings`、`sidebar`、`skills`、`workspace-browser` 等）、`scripts/` 静态门禁、`package.json` 的 `lint` |
| 出现次数 | 1 |
| 关联 | 提交 `d13c3b22e`（S1）、`5e6394e22`（S2）、`76fe91709`、`12e0bf728`（S4），本地提交，未 push |

### 现象

1. 用户气泡的动作行（复制 / 编辑 / Fork / Rewind，Rewind 的唯一入口）写作 `opacity-100 sm:opacity-0 sm:group-hover:opacity-100`：用宽度 `sm`（≥640px）充当「有没有悬停」的判据，平板与横屏手机宽度够大却没有悬停，整行不可见；键盘聚焦到行内按钮时也不会显现；
2. 同类写法在 41 个组件文件里共 46 个功能控件单元（删除、复制、下载、移除、打开、重命名等）：只有 `group-hover`、`sm:` / `md:` 宽度门，或 `isMobile`（`useIsMobile()`，≤768px）三元三种之一；
3. `bun run lint` 里没有任何门禁拦截 TSX 里绕过 i18n 的用户可见字面量。

### 根因

1. 宽度断点被当作输入方式的代理，而宽度与是否有悬停无关；
2. `opacity-0` 的控件只写了 `group-hover`，没有 `group-focus-within`，键盘用户没有显现路径；
3. 项目规则（文案必须中英双语）只靠人工检查，没有机器门禁。

### 修复

1. `lib/utils/a11y.ts` 新增 `REVEAL_ON_HOVER = 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100'`：鼠标悬停、键盘聚焦到所在 `group`、粗指针触屏三条路径任一成立即可见；命名组（`group/img` 等）无法复用常量，就地写带同名后缀的三个变体；
2. S1：用户气泡动作行改用常量；附件下载按钮在 HEAD 里已有同样三个变体的内联写法，改为引用常量（行为不变）；补两处测试固定三条显现路径；
3. S2：41 个组件文件的 46 个功能控件单元改用常量（命名组 `img` / `obj` / `dep` / `att` 就地写三变体）；`PortalTabs` 保留 `isActive && 'opacity-100'`，`MermaidChart` 在 `alwaysVisible` 时不加常量，`ChatHistoryRow`、`WikiConceptTree` 等去掉 `isMobile` 分支；
4. S4：`scripts/hardcoded-copy-scan.ts`（TypeScript AST 找 JSX 文本、JSX 表达式里的字符串字面量与承载文案的属性）+ `scripts/check-hardcoded-copy.mjs`（按文件计数的棘轮：增加失败，改善未更新基线也失败，`--write-baseline` 才重写；比较规则抽成可单测的 `hardcoded-copy-ratchet.ts`）接入 `bun run lint`，即 CI 的 Oxlint 步骤；目录遍历抽到 `scripts/source-files.mjs`，`check-theme-colors.mjs` 共用，输出与重构前逐字一致；
5. 文档：`lib/utils/_ARCH.md`、`message-box/_ARCH.md`、`image-editor/_ARCH.md`、`wiki/_ARCH.md`、`scripts/_ARCH.md`、前端根 `_ARCH.md` 同步；根仓库 `topic_09` roadmap 里 3 行 `UserMessage*.tsx` 行号引用改成现状（根仓库提交 `0dcf3f263`；`topic_06` 里原有的一处引用在我动手前后被他人重写移除，没有处理）。

保留不动：32 个非控件单元（悬停才出现的装饰箭头、拖动图标、图表柱高亮与说明文字，本身不可点击）；两处由 JS 状态控制的悬停显现（`kanban/KanbanTaskCard.tsx` 的 `showActions`、`memory/cards/MemoryCard.tsx` 的勾选框）；`OrgMarketplace` / `TemplateMarket` 的「已安装」状态指示（是指示不是控件）。

### 验证

1. 真实 Chrome（patchright 驱动的无头 Chromium，触屏用 `has_touch + is_mobile` 模拟）：用项目的 `@tailwindcss/postcss` 编译真实 `globals.css`，确认 8 个相关类（含 `obj` / `dep` / `att` / `img` 命名组变体）都由源码生成；隔离页面里用从 `a11y.ts` 读出的常量原文：桌面 1280 鼠标默认 opacity 0、悬停 1、移开 0，Tab 聚焦 1、失焦 0，命名组同样；触屏平板 1024×768、横屏手机 844×390、竖屏手机 390×844 默认都是 1（`pointer: coarse` 为真）；对照组 `opacity-100 sm:opacity-0 sm:group-hover:opacity-100`（旧写法的代表）在平板与横屏手机上为 0，在桌面 1280 上 Tab 聚焦后仍为 0；另测 `opacity: 0` 的按钮在桌面鼠标与触屏点按下都照常触发点击，所以此前看不见的控件同样会被误触，这次只改可见性、不改点击行为；
2. 测试：`vitest related` 覆盖改动文件 87 个文件 765 例通过（工作区）；`scripts/__tests__` 6 个文件 57 例通过；
3. 静态：oxlint 对 41 个 S2 文件与新增脚本 0 error、9 条既有 warning（`no-img-element` 等）；prettier 对新增与改写的文件无差异；`tsc` 仅余他人未提交测试里的一处无关报错（`kanban/__tests__/KanbanTaskHandoffSection.test.tsx(68,3)`）；本地行数自检报告的 24 个新增超限文件里没有我改的文件；我改的文件中有 18 个本就超过 400 行（在既有基线内），每个净增不超过 7 行（`LocalPathsConfig.tsx`）；
4. S4：基线取自已提交树（369 个文件、3550 处），扫描 1437 个 TSX 文件用时 5.1–9.3s；在已提交树的导出里加一个含中文与英文属性的合成文件，门禁失败并列出 `文件:行 [kind] 文案`，删除后恢复通过；固定种子抽 30 处人工核对，29 处是真实硬编码文案，1 处（`t('apiKey') || 'API Key'` 的回退值）算误报，精度约 97%（样本里 23 处在 `memory/command-center`，其余目录只有 7 处，召回率没有测）；
5. 在已提交树的导出里模拟 CI 的 lint 链：`verify:stable-mocks`（1130 个测试文件）、`verify:theme-colors`（2457 个文件）、`verify:hardcoded-copy` 通过；`verify:a11y` 失败（豁免注释 81→82，另有三项已改善未收紧基线），在我的提交之前的树上同样失败、输出一致；豁免数 81→82 的来源是 `memory/cards/MemoryCard.tsx` 里新增的一条同时豁免两条规则的注释（提交 `2fdaa87f8`，他人），没有处理。

### 踩坑经验

1. 对照组要先确认它的 CSS 真的被编译出来：第一版探针里旧写法的 `sm:opacity-0` 没有任何源码使用，Tailwind 没生成它，对照组在桌面上也显示为可见，看上去像是旧写法没问题；用 `@source inline(...)` 强制生成后对照才成立；
2. 批量改写前先用 AST 枚举，再逐个判定「功能控件」还是「装饰」：第一版估算「>20」，实际 46 个功能单元、32 个非控件单元；codemod 还误匹配过同一容器里的说明文字与删除按钮，要加标签与附加类名过滤；
3. 棘轮基线必须取自已提交树：工作区比 HEAD 多出他人未提交的新文件，直接写基线得到 522 个文件、5550 处，而已提交树是 369 个、3550 处；
4. jsdom 里 `localizeReactNode` 只渲染「中文 / English」的一侧，`title="复制 / Copy"` 在测试里是 `Copy`，查询要用后者；
5. 共享工作区提交：用独立索引 + `git apply --cached --unidiff-zero` 只应用我的 hunk，`ArtifactCard`、`GoalStatusExpanded`、`lib/utils/_ARCH.md` 三个文件混有他人改动，按关键字过滤 hunk，提交后用「提交内容里没有他人符号」和「工作区残差只剩他们的行数」核对；
6. 局限：没有在真实聊天页验证（后端 :8000 未启动，浏览器 MCP 也拒绝应用地址），只验证了编译后的常量在隔离页面里的行为，触屏是模拟不是真机；触屏设备现在总是显示这些控件（设计变更，例如 iPad 上的侧栏行），其中带破坏性的几个（`MemoryTrashPanel` 的永久清除、`AgentFaqTab` 删除、`LocalPathsConfig` / `ProviderList` 移除等）是否都有二次确认没有逐个核对；窄桌面窗口用鼠标时，原先 `isMobile` / `sm:` 分支下常显的控件现在改为悬停或聚焦显现；扫描器只覆盖直接写在 JSX 里的字面量，不含对象 / 数组常量再渲染的文案、`toast` / `Error` 消息和 `.ts` 文件，存量只是冻结没有清零；实测已提交树的 `.tsx` 里含 CJK 的字符串字面量共 1431 处，扫描器覆盖约 683 处（47.7%，按行号与文案前缀匹配的近似值），其余 748 处（126 个文件，437 处在对象属性值、132 处在调用参数、73 处在 JSX 之外的三元、61 处在数组）不在门禁范围内，把文案挪进这些位置会让门禁「变绿」而问题仍在（古德哈特风险），后续要扩大覆盖面需要先重新抽样核对精度；本地工作区里他人未提交的新文件会被新门禁拦下（新文件基线为 0），需要他们提交前处理；`check-a11y-ratchet.mjs` 自带的目录遍历没有并入共享的 `source-files.mjs`；`specialty-suites-gateway` 缺 `_ARCH.md`（他人未提交）使 `check_fractal_docs.py` 在工作区失败。

---

## BUG-AGENT-2026-10-14-007: 词条链接面板切换词条后仍显示上一个词条的链接、迟到响应覆盖新词条，失败时展示服务端英文消息；快速连点词条后详情与所点词条不一致；面板每次打开都多算一份无人需要的局部图谱

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（展示与所选词条不一致、失败提示未本地化；不丢数据） |
| 影响范围 | 前端 `wiki/WikiConceptLinksPanel.tsx`、`wiki/useWikiConceptsList.ts`、`wiki/useWikiConceptClaimActions.ts`、`services/wiki/service.ts`、6 语言 `locales`；server `app/api/wiki/router.py` 的 `/wiki/concepts/{name}/links`；harness `toolkits/wiki/retrieval/{graph_store,indexer,edge_links,graph_analysis}.py` |
| 出现次数 | 1 |
| 关联 | roadmap topic_02 #140 第三批补修；BUG-HARNESS-2026-10-14-007 |

### 现象

1. 面板在词条切换后继续显示上一个词条的出入链，直到新响应到达：骨架屏只在首次加载出现（`loading && !linksData`），详情标题已是新词条、下面的链接却属于旧词条；快速连续切换时，较早发起的响应后到会覆盖较晚的。
2. 加载失败时面板展示服务端消息原文（`Failed to fetch concept links`），六种语言的用户都看到英文；同一个面板里本来就有本地化的 `loadFailed`。
3. 词条树里快速连点两个词条：较慢的响应后到，会覆盖后点的词条，详情与所点不一致且没有任何提示；切换 Agent 范围后，在途的选择请求还会把旧范围的词条写回来。
4. 面板的「关联概念」页签只是本地 40 点邻域，与词条树、3D 图谱和出入链列表重复；每次打开面板，`get_concept_links` 为它多做一次 BFS（合成 300 页库上约占一次打开 5.24 ms 中的 3 ms，这只是量级，不是性能声明）。
5. 接口里 `weight`、`line_number` 前端没有任何读取（编辑器 `lineNumbers` 为 `off`，行号用户对照不了）；出链的 `context_snippet` 恒为 `null`；`source_systems` 会写出 `system:*` 伪边，没有任何读取方，读它的各处（`edge_links`、`graph_analysis`、`link_extraction`）都在给它让路，资料文档还把它写成「血缘追溯」。
6. 在词条详情里执行声明状态更新、证据修复、保存或删除后，请求返回前改选了另一个词条：迟到的刷新把详情改回操作前的词条（保存还会连带重置编辑区与草稿基线），删除返回后会把刚选的新词条清空，详情区变成空白；删除期间打开被删文件夹下的词条时，详情仍停在已被删除的词条上。

### 根因

1. 面板是单个组件，`fetchLinks` 依赖 `conceptName` 重新拉取，但 `linksData` 不随词条清空，也没有对「已不是当前词条」的响应做丢弃。
2. 错误状态存的是 `err.message`，渲染时 `{error || t('loadFailed')}` 在有消息时总是用消息。
3. `handleSelectConcept` 没有「只认最后一次请求」的保护，重置 Effect 也不让在途请求失效。
4. 局部图谱、`weight`、`line_number` 是面板最初的设计留下的，后来页签文案与展示都改过，数据却一直在产出。
5. 声明状态更新、证据修复、保存在 `await` 刷新之后无条件写入选中词条，删除在 `await` 之后用发起时的 `selectedConcept` 快照判断是否清空，都不看期间详情是否已换成别的词条；`selectRequestRef` 只守住了 `handleSelectConcept` 一处写入。

### 修复

1. 面板拆成外层与内层：外层持有页签选择，内层以「Agent 范围 + 词条」为 key 挂载，切换词条即丢弃旧数据与在途请求、从骨架屏开始，页签选择跨词条保留；内层用请求计数让刷新与卸载后的迟到响应失效。
2. 失败只展示 `loadFailed`。
3. `useWikiConceptsList` 里 `selectRequestRef` 计数：只有最后一次发起的选择写入状态、弹错误提示；重置 Effect 同样让在途选择失效。
4. 删除「关联概念」页签与它的整条数据：前端类型与 `getConceptLinks` 的 `depth`、server 的 `depth` 查询参数与 `ego_graph` 字段、harness 的 `get_concept_links(depth)` 与 BFS 调用、4 个语言键 ×6 语言；`/wiki/graph` 与它的模型保留（3D 图谱在用）。
5. 出链只带 `name`、`exists`，入链另带 `context_snippet`、`heading`（server 与前端各拆成基础类型与入链类型）；`_extract_mention_record` 只返回 `(片段, 小节)`；`weight` 只留在 SQL 排序里。
6. 删除 `source_systems` → `system:*` 伪边的生产者（`indexer._source_system_targets` 及 `yaml`、`load_frontmatter_metadata` 导入）与 `edge_links` 里为它加的过滤；`source_systems` 仍是 metric 页面的前置校验字段（`frontmatter_contract.py:177`），只是不再写边；资料文档里「血缘追溯」的说法同步改为如实描述。
7. 新增 `shownConceptNameRef`：详情区正在展示的词条名，由包装后的 `setSelectedConcept` 在每次写入时同步维护（`selectedConcept` 的全部写入点都经过它）。声明状态更新、证据修复、保存三条操作返回时，只有展示的词条仍是操作对象才写入（保存还跳过编辑区与草稿基线的重置）；删除返回时按展示的词条名判断是否清空（含被删文件夹下的词条），不再用发起时的快照；写入已成功的提示与 `onVaultMutated` 照常触发。声明操作 hook 通过 `shownConceptNameRef` 入参共用这个判断。

### 验证

1. 先红后绿：前端 7 例失败（面板 4 例、选择 hook 3 例）、harness 3 例、server 3 例，原因都与预期一致，修复后全部通过；新增的前端用例在旧代码上分别复现了「旧词条数据残留」「迟到响应覆盖」「服务端英文消息」「乱序选择」「切换范围后写回」。随后补的四条操作（声明状态更新、证据修复、保存、删除）先红后绿：前端 4 例在旧代码上失败（刷新迟到覆盖新选择 3 例、删除迟到清空新选择 1 例，断言都是「选中仍是后选的 B」），另有 2 个对照用例（无改选时刷新照常落地、无改选时删除照常清空）在旧代码上即通过，用来防止守卫过头。第一版用选择计数做判断，对抗审查补了 2 例并改成按展示的词条名判断：操作期间重新点同一个词条时刷新应落地（计数版先红：详情停在操作前的数据）、操作期间打开被删文件夹下的词条时删除后应清空详情（计数版先红）；保存用例另断言编辑区不被迟到的刷新改写，把编辑区写入的守卫拿掉后该用例失败。
2. 前端 `knowledge` 目录与 `services/wiki` 22 个文件 116 例通过；harness `tests/toolkits/wiki` 全量 859 例：第一次全量 857 通过，失败 2 例，其一是漏改的 `_extract_mention_record` 解包（`test_wiki_alias_and_chinese_anchor.py`，已修，该文件与 `test_concept_links.py`、`test_link_edges.py`、`test_frontmatter_contract.py` 共 49 例重跑通过），其二是调用真实 LLM 的 `test_sidecar_integration::test_sidecar_build_index_query_pipeline`（单独重跑超过 120s 超时，日志里是访问 raw.githubusercontent.com 的 `ConnectTimeout`，与本条无关）；server 链接单测与集成测试 5 例通过。
3. 静态：`ruff check` / `ruff format --check`、`mypy`（3 个 harness 模块）、oxlint、prettier、`verify-i18n.mjs` 通过；`tsc --noEmit` 全量只报他人文件的错误（`KanbanTaskHandoffSection.test.tsx`、两个 `xai` 凭据测试），本条文件无报错。
4. 局限：没有在运行的应用里看过面板（只改了页签数量，容器查询类名未动）；没有测真实 vault；旧索引里已存在的 `system:*` 边行没有迁移，该页下一次被写入时会随整页边的替换消失（`source_systems` 没有出现在任何提示词里，实际写入概率低，未测真实库）。

### 踩坑经验

1. 删一个私有函数的返回值字段，要连测试里的解包点一起查：`test_wiki_alias_and_chinese_anchor.py:74` 与 `test_frontmatter_contract.py` 里固化旧行为的用例只在全量运行里暴露，只跑自己改的几个文件不够；
2. 「生产者没有读取方」的数据，会让下游到处加过滤给它让路；先查有没有真正的读取方，没有就删生产者，而不是继续补过滤；
3. 面板「切换词条」的正确性用「按词条 key 挂载」从结构上解决，比在一个组件里手工清空状态加取消标志更不容易漏；页签选择放到外层，才不会因为重新挂载而丢；
4. 后台起测试时 `( 命令 ) &` 在这个环境里会随工具调用结束被回收且没有任何输出，要用工具自带的后台模式；
5. 共享工作区：6 个语言文件被他人整体重写，只提交本条的 4 个键、每个语言各自在 HEAD 内容上做同样的删除（先用 JSON 等价检查），不碰他们的行。
6. 给「只认最后一次」加保护时，要先列出这份状态的全部写入点再逐个守卫：本条第一轮只守了 `handleSelectConcept`，之后对 `setSelectedConcept(` 与 `getConcept(` 做全仓检索才发现保存、声明操作、删除三处旁路；
7. 操作回调里读到的 `selectedConcept` 是发起时的闭包快照，`await` 之后拿它做判断（比如「删的是不是当前选中的」）会把已经改选的状态当成没变；需要「现在展示的是谁」时，用同步维护的 ref，不要用快照，也不要用 effect 去镜像 state（提交与 effect 之间的间隙里迟到的结果仍会读到旧值）；
8. 用「请求计数」判断迟到的操作结果会误伤同一个对象：操作期间重新点同一个词条也会让计数变化，刷新被丢弃，详情停在操作前的数据。判断「结果还属不属于当前展示」应当比较对象本身，计数只适合「只认最后一次」的选择请求。

---

## BUG-AGENT-2026-10-14-008: xAI SuperGrok 订阅登录：访问令牌到期后仍带旧令牌发请求、模型页探测把占位符当密钥发给上游、重启后登录标志被重置、三处设备码登录各写一套

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（只影响用订阅登录的用户：令牌到期后的模型请求与模型页探测失败、重启后登录标志与另外两项用户设置被重置；不丢数据） |
| 影响范围 | server：`app/services/agent/oauth_token_policy.py`（新增）、`provider_oauth_tokens.py`（新增）、`oauth_refresher.py`、`app/services/integrations/oauth_store.py`、`app/core/channel_bridge/config_loader.py`、`app/api/integrations/{llms,provider_oauth,xai_oauth}.py`、`app/server/lifespan.py`；harness：`toolkits/llms/adapters/chat_model/{session_affinity,api_key_refresher,payload_debug}.py`（新增）、`model.py`、`async_mixin.py`、`api/hooks.py`；frontend：`services/{xai-oauth,provider-oauth,provider-oauth-reconcile}.ts`、`services/config/configNormalizer.ts`、`store/useProviderStore.ts`、`store/config/{providerSubscription,subscriptionDefaultModel}.ts`、`hooks/shared/{useXaiDeviceLogin,useCopyFeedback}.ts`、`NoProviderBanner.tsx`、`ProviderOAuthSection.tsx`、`ProviderConfig.tsx`、`CredentialsDialogs.tsx`、`useCredentialsOAuth.ts`、六语言 `locales` |
| 出现次数 | 1（读代码、探针与单元测试确认；没有真实 SuperGrok 账号，授权流程与上游行为没有做端到端验证） |
| 关联 | `BUG-AGENT-2026-10-13-007`（订阅登录下线后的遗留；本条补上其中记录的横幅失败路径写不进错误、原样展示服务端错误文本）· roadmap topic_07 订阅登录条目（引用的路径与路由同步更正） |

### 现象

1. 访问令牌的新鲜度没有任何环节负责：`load_user_configs` 把库里的令牌原样注入提供商配置（HEAD `config_loader.py:245`），不看它是否临近到期；一轮 Agent 对话可能比一个访问令牌活得久，已创建的模型实例整轮沿用同一个令牌。
2. 注入发生在默认模型解析之后（HEAD `config_loader.py:233` 先于 `:245`）：只有订阅、没有任何 API Key 的用户，解析默认模型时提供商手里没有凭据。
3. 登录、断开、刷新写库后，已加载配置的缓存快照（30 秒）不失效（`persist_credentials_locked` 提交后什么也不做），三种操作在缓存期内都看不到结果。
4. 模型页对订阅提供商做验证、可达性检查与速度测试时，把占位符 `__myrm_oauth_token__`（`providerTypes.ts:405`）当 API Key 原样发给上游，服务端没有解析占位符的位置。
5. 刷新失败没有记忆：被提供商拒绝的刷新令牌每次调用都再试一次（对会轮换刷新令牌的发行方，重试本身就是消耗），上游故障时每次 LLM 调用都打一次令牌端点；调用方被取消时刷新请求跟着取消，若提供商此时已轮换，新的刷新令牌可能来不及落库。
6. 内置提供商规范化只保留五个字段（HEAD `configNormalizer.ts` 的 `mergeProviders`）：每次启动把 `oauthConnected`、`credentialPoolStrategy`、`egressProxy` 重置为出厂值，订阅用户重启后被当成未登录。
7. 设备码登录有三份实现（聊天横幅、模型页、凭据页），轮询间隔、`slow_down` 处理、超时、失败提示各不相同；横幅把 `grok-2` 等固定 id 写死为登录后的启用模型（`NoProviderBanner.tsx:21-22`），凭据页 xAI 对话框的中英文案写死（硬编码文案棘轮里该文件 12 处）；服务端同时有两套登录端点（`/integrations/provider-oauth/xai/{start,poll}` 与 `/integrations/xai/oauth/{start,poll}`）和两套状态 / 断开端点，状态接口还返回写死的模型名。
8. 原生 xAI 端点的请求不带会话路由头 `x-grok-conv-id`，同一会话的多次请求不保证落到同一台服务器，不利于提示词缓存命中。

### 根因

1. 刷新只存在于会话级工具凭据的 `refresh_callback`；LLM 请求用的注入令牌没有刷新入口，注入位置也在默认模型解析之后。
2. 配置快照的失效点只覆盖配置写入，没有覆盖 oauthCredentials 这条会注入进快照的数据。
3. 占位符是前端约定，服务端没有对应的解析与主机校验。
4. 刷新器没有失败分类：终态拒绝与可重试故障走同一条路径，取消语义由调用方决定。
5. 内置提供商的合并写成显式字段清单，新增字段不会让任何东西报错，只是每次启动被悄悄重置。
6. 登录流程按界面各写一份，没有「已连接」变成提供商状态的唯一位置，也没有对启动模型的单一来源。

### 修复

1. server：新增 `oauth_token_policy.py`（纯函数：到期取 JWT `exp` 与 `now + expires_in` 的较早者、5 分钟提前量、刷新失败分为终态 / 可重试：只有 4xx 且响应体是 OAuth 错误——JSON 里带非空字符串 `error`，RFC 6749 第 5.2 节——才算终态，网关 / 代理 / 防火墙返回的无 OAuth 错误体的 4xx 与超时、限流、5xx 一样可重试）；`xai_oauth.py` 登录时用同一解析写 `expires_at`。
2. server：新增 `provider_oauth_tokens.py`——提供商到发行方的唯一登记 `PROVIDER_OAUTH_ISSUERS`；`resolve_oauth_marker` 把占位符换成存库令牌（只发给签发主机，10 秒预算）；`refresh_provider_oauth_credentials` 在配置加载期刷新到期令牌（2 秒预算，超时沿用原令牌，刷新在后台继续并自行落库）；`freshen_api_key` 供 harness 在请求前续期（只认本进程签发过的令牌，最多记 16 个，其余密钥只做一次字典查找）。
3. server：`config_loader.py` 先刷新到期令牌再注入，并把注入提前到默认模型解析之前；`oauth_store.persist_credentials_locked` 提交 oauthCredentials 后失效已加载配置快照（失败只记 warning，不掩盖已提交的写入）。
4. server：`oauth_refresher.py` 按指纹记住被拒绝的刷新令牌（新登录换新令牌即解除）、可重试失败冷却 30 秒、刷新作为独立任务 `asyncio.shield`、终态失败照常发（去重的）重新授权事件。
5. server：`llms.py` 的 `/verify`、`/check-reachability`、`/speed-test` 在建模型前调 `resolve_oauth_marker`；未连接或目标不是签发主机时，`/verify` 返回 502、可达性检查报不可达、测速对应项报错，三者都不碰上游。
6. server：路由收敛——删除 `provider_oauth.py` 里 `/xai/{start,poll}` 的转发与 `xai_oauth.py` 里的 `/status`、`DELETE`，状态与断开统一走 `/integrations/provider-oauth/{status,disconnect}/{provider}`，状态不再返回写死的模型名；`/poll` 对 `expired_token` 返回 `expired`（此前与拒绝同为 `denied`）。
7. server：`lifespan.py` 启动时通过 `myrm_agent_harness.api.hooks.set_api_key_refresher` 登记 `freshen_api_key`（失败只记 error，不阻塞启动）。
8. harness：新增 `api_key_refresher.py`（进程级登记，异步路径每次请求前 `renew_api_key`），`model.py`、`async_mixin.py` 接入，`api/hooks.py` 导出 `set_api_key_refresher`；新增 `session_affinity.py`（按主机匹配原生 xAI 端点后注入 `x-grok-conv-id`，取 `prompt_routing_key_var`，没有则取 `chat_id_var`，调用方已设同名头时不覆盖）；`payload_debug.py` 从 `model.py` 拆出，两个文件回到行数上限内（基线 `async_mixin.py` 579→553、`model.py` 552→514）。
9. frontend：`configNormalizer.ts` 的 `BUILT_IN_FIELD_OWNER` 是 `Record<keyof ProviderConfig, 'definition' | 'user'>`，新增字段时编译期强制决定归属，`mergeBuiltInProvider` 保留全部用户字段。
10. frontend：`provider-oauth-reconcile.ts` 在启动（`initProviders` 成功路径）用服务端状态校正 `oauthConnected`，只改这个标志，比较基准是请求发出时的标志，请求期间完成的登录 / 退出不会被较早的回答覆盖；离线时什么都不改。
11. frontend：`useXaiDeviceLogin.ts` 是唯一的设备码流程（RFC 8628：`slow_down` 追加 5 秒、最小间隔 1 秒、设备码寿命到期、卸载即停、重复 start 忽略），失败原因是封闭集合 `startFailed | expired | denied | timeout`，各界面映射成本地化文案；`providerSubscription.ts` 是应用内登录 / 登出变成提供商状态的唯一位置（连接：置标志，按 models.dev 目录挑启动模型并启用，已有选择不动；断开：没有其他凭据的提供商被禁用并释放绑定的模型位，有 API Key 的继续可用）；`subscriptionDefaultModel.ts` 取目录里最新的、未弃用、支持工具调用且输出文本的模型，不再写死 id。
12. frontend：横幅、模型页订阅卡片、凭据页 xAI 对话框改用同一个 hook 与同一份副作用；凭据页对话框文案进六语言 `locales`（硬编码文案棘轮里该文件 12→2，剩下 2 处是另一个对话框既有的中英并列文案）；复制反馈抽成 `useCopyFeedback`；外链用 `noopener,noreferrer` 打开；`xai-oauth.ts` 只剩设备码 start / poll，`provider-oauth.ts` 只剩状态与断开。

行为说明：

1. 显式断开订阅时，没有其他凭据的提供商会被禁用并释放它占用的模型位；有 API Key 的提供商保持启用。
2. 启动校正只改 `oauthConnected`，不启用 / 禁用提供商，也不动模型选择。
3. 连接成功时 models.dev 目录不可用：提供商已连接但不启用，成功视图照常显示，用户到模型页自选模型。
4. 刷新被拒绝只认 OAuth 错误体：4xx 但响应体不是带 `error` 字符串的 JSON（代理 / 防火墙拦截页、网关自己的 JSON）按可重试处理，不记住刷新令牌、不发重新授权事件。若某个提供商用非 OAuth 格式的响应拒绝刷新令牌，它同样按可重试处理（每 30 秒最多再试一次，不弹重新授权），而不是被永久阻断。

### 验证

1. server：本次触及的 10 个测试文件加 e2e 文件共 187 例通过（4 例 e2e 按标记取消选择）；刷新器、会话凭据、`config_loader`、Google Workspace 同步、LLM 探针与 OAuth 接口相关的 18 个测试文件共 191 例通过（其中 `test_provider_oauth_tokens.py` 含服务端占位符与前端 `OAUTH_AUTH_API_KEY_MARKER` 字面量一致的检查）；新增 `test_oauth_token_policy.py`、`test_oauth_refresher_failure_memory.py`、`test_provider_oauth_tokens.py`、`test_llm_oauth_marker.py`、`test_lifespan_oauth_refresher.py`，并在 `test_oauth_store.py` 补了「明文原样存、密文进 `_cipher` 信封」2 例。
2. harness：`test_api_key_refresher.py`、`test_prompt_routing_key.py`、`test_chat_model_stream_edges.py`、`test_integration_surface.py` 共 79 例通过；`set_api_key_refresher` 经公开门面登记后与 `renew_api_key` 读到同一份登记（门面测试 1 例）。
3. frontend：广域 vitest 346 个文件 2055 例通过（聊天窗口、设置 / 模型服务、凭据页、`hooks/shared`、`store`、`services/config`、`services`）。
4. 变异检查（临时改写源码、跑测试、恢复原文）：server 刷新失败记忆 6 个、占位符解析 3 个、`_ttft_sort_key` 1 个、存储形状（信封、键名、加密标志）3 个，harness 路由头 3 个、续期登记 5 个，全部杀死；frontend 第三批共 68 个：第一轮 52 个，杀死 50 个，存活 2 个——冗余的重读守卫经分析后删除，失败提示残留改成让重试保持挂起再断言后在第二轮杀死；第二轮 16 个，全部杀死；复核阶段对刷新失败分类 4 个（退回旧规则、空 `error`、非字符串 `error`、忽略可重试的 OAuth 错误码）与占位符字面量漂移 1 个做变异（只改解释器内存里的模块源码，工作树不动），全部杀死。
5. 静态：`ruff check` / `ruff format --check`、mypy（server 9 个源文件、harness 6 个源文件均无报错）、oxlint、prettier、ReadLints 对触及文件均通过；`verify-i18n.mjs` 通过；`tsc --noEmit` 只剩他人的两处错误（`KanbanTaskHandoffSection.test.tsx(68,3)`、`app/zz-adm-preview/Preview.tsx(89,31)`）；`verify-i18n-references.mjs` 的 219 个缺失 key 与此前记录的基线数目相同，没有一条出自本次文件。
6. 门禁：本次的 server 文件没有新增 harness 深层导入（逐文件对照基线）；`test_server_harness_imports.py`、`test_api_route_consumers.py` 的现有失败都出自他人新增的导入与路由，没有一条涉及本次的路径与路由；`check-hardcoded-copy` 的 drift 提示里 `CredentialsDialogs.tsx` 12→2 是本次的改善，基线已同步收紧。
7. 局限：没有真实 SuperGrok 账号与浏览器，设备码授权的端到端流程只有单元测试与前端交互测试；`x-grok-conv-id` 只验证了注入条件，没有在真实接口上量化缓存命中的变化；刷新锁是进程内 `asyncio.Lock`（既有设计），多个服务进程同时读写同一份库时不保证串行；`llms.py`、`lifespan.py`、`useProviderStore.ts` 本来就超过 400 行，本次只在其中加了调用点。

### 踩坑经验

1. 令牌「注入」与「新鲜」是两件事：注入点之前要有刷新点，注入点之后的长寿命对象要有续期钩子；配置加载被就绪探针以 3 秒截止时间等待，加载期预算必须更小（2 秒，超时沿用原令牌），LLM 调用与模型探针才能给完整的令牌交换时间。
2. 服务端新增对 harness 的深层导入会被棘轮拦下，正确做法是经 `api.hooks` 导出并同步 `__all__`、`_ARCH` 与门面测试，而不是改基线。
3. harness 的 `agent/security/__init__.py` 用 `__getattr__` 惰性导出类，mypy 把它们当变量，报 `not valid as a type`并级联出 `func-returns-value`；从定义模块 `agent.security.types` 导入即可，该路径已在基线内。
4. 校正类逻辑要拿「请求发出时」的本地值与服务端答案比较，才不会让慢响应覆盖请求期间完成的登录；这一条靠「请求期间改动对象再让响应返回」的测试固定下来。
5. 失败提示的测试要断言在中间状态上（重试进行中旧提示已消失），等流程走完再断言会被等待视图掩盖，变异检查正是这样发现的。
6. 共享工作区里多个 harness / 前端文件夹带他人改动：用 HEAD 内容加自己的精确替换生成补丁，只提交自己的 hunk。

---

## BUG-AGENT-2026-10-14-009: 技能「Shadow A/B 验证」整条链没有产出过结论，却在详情页提供一键启动并按会话对半分流；质量分是 0.5 占位；优势材料据此宣称有「影子对照」闸门

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（名不副实且有线上副作用：详情页能启动 A/B，运行期间 harness 把会话对半分给候选版本，而这条链拿不到可用结论；材料对外宣称它是验证闸门） |
| 影响范围 | harness `backends/skills/decorators/`、`agent/skills/optimization/`、`agent/skills/evolution/core/`、`agent/streaming/broadcast/`；服务端 `app/services/skill_optimization/`、`app/adapters/skill_optimization/`、`app/api/skill_optimization/`、`app/database/models/skill_optimization/`、`app/lifecycle/`、`app/database/migrations.py`；前端 `SkillQualityGuardian`、`services/skill/optimization.ts`、六种语言文案；根仓库优势材料与路线图 |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-14-003` / `004` / `005`（逐步删除这条链上不可达的部分；005「保留不动」里的 Shadow A/B、晋升门禁、质量快照三件套、优化记录两件套，这次核实后一并删除） |

### 现象

1. 技能详情页的「质量守护」面板可以对一个技能启动 Shadow A/B；运行期间 `VersionAwareSkillBackend` 按会话把 50% 粘性分流给候选版本；
2. 这条链没有产出过结论：影子回放的触发按错误的工具名匹配；回放执行时在智能体工具列表里按技能 ID 找同名工具，而技能是以文档形式经 `skill_select_tool` 注入的，工具列表里只有 `skill_market_tool`、`skill_manage_tool` 这类元工具，找不到就返回 error；
3. 运行均值从未落库；版本表的 `quality_score` 在没有真实样本时回落到 0.5 常量 `_NEUTRAL_QUALITY`（005 已把它从对比 / 详情接口的返回里摘掉，写入路径仍在）；
4. `skill_shadow_samples`、`skill_ab_test_results`、`skill_optimization_records`、`skill_quality_history` 四张表和 `skill_versions.quality_score` 只被这条链读写；
5. 优势材料把它写成已经验证过的「影子对照 / 晋升闸门」。

### 根因

1. 链路按设想一次搭完，没有和「技能是文档、不是可调用工具」这一事实对账，回放因此无处可跑；
2. 004、005 只删了不可达的部分，保留了「已接线」的部分；「已接线」不等于「能产出结论」，没有把入口一路走到出口核实；
3. 材料按设想写，没有回到代码核实。

### 修复

纯删除，没有新增能力：

1. harness（`e556569995`，37 个文件，+284 / −3313；`75d932b8f6` 更正装饰器目录的依赖清单）：`VersionAwareSkillBackend` 只返回已激活快照或文件系统基线，删除 `forced_version_var`、`resolved_skill_versions_var`、`ABTestStoreProtocol` 与粘性 A/B 分支（系统提示里的技能列表本来就不经版本路由，提示缓存不受影响）；删除 `ToolCallEventData.version` 及其广播接线；`skills.optimization` 只留版本历史协议 / 类型与内容安全校验，`ab_test`、`optimizer`、`observability`、`event_emitter`、`event_adapter`、`result_comparator`、`quality_calculator` 删除；`build_change_manifest` 搬到 `evolution.core.change_manifest`，删除晋升判定 `evaluate_promotion_gate`；
2. 服务端（`27021dbd0`，70 个文件，+202 / −3836）：删除影子测试、A/B 管理、晋升门禁、语义比对、执行提供者与运行时，四个 A/B 仓库与转换器，A/B 路由，四个模型，生命周期接线与 `SKILL_AB_TEST_UPDATED` 事件，以及对应测试与架构基线；
3. 迁移：在 `MIGRATION_STATEMENTS` 末尾追加四条 `DROP TABLE IF EXISTS` 和 `ALTER TABLE skill_versions DROP COLUMN quality_score`，新增 `tests/database/test_skill_shadow_verification_tables_retired.py`（升级库与全新库各一例）；
4. 前端（`a92fba6bc`，18 个文件，+3 / −1125）：删除 `SkillQualityGuardian` 及详情页挂载、`optimization.ts` 里的 A/B 启动与质量分类型、`skill_ab_test_updated` 透传事件、六种语言里的守护 / A/B / 质量分文案以及携带它们的翻译补丁；
5. 文档：根仓库优势材料与两份路线图里的相关说法改成代码事实（`31acd520f`，9 个文件，+50 / −53）；公开文档在更早的提交里已同步。

保留不动：回归过滤、变更清单 `build_change_manifest`、审批卡（`testPassed` / `verificationProof` / 影响范围）、带快照的原子应用与一键回滚、版本历史面板、Eval Lab 三臂对比 `app/core/eval/skill_ab.py`、`session_id_var`。

### 验证

1. harness：已提交内容的干净导出里，`tests/backends/skills`、`tests/agent/skills/optimization`、`tests/agent/skills/evolution`、`tests/agent/streaming/broadcast` 共 1087 通过、3 跳过；`ruff check` 对相关源码与测试目录无告警；
2. 服务端：已提交内容的干净导出里，版本快照仓库、SQLAlchemy 存储、`api/skill_optimization`、`services/skill_optimization` 与两个表退役测试共 43 例通过，`test_no_user_id` 与 `test_outbound_model_calls` 7 例通过，`ruff check` 对改动目录无告警；
3. 前端：已提交内容的干净导出里，`tsc` 只剩一条（导出里没有 `myrm-agent-extension` 目录造成的模块缺失），技能 / 服务 / 全局事件 / 版本来源相关 105 个测试文件、553 例通过，`verify-i18n` 在我的提交前后输出逐行一致（失败项是他人未翻译的词条）；工作区 `tsc` 只有一条他人的看板测试报错；
4. 迁移：升级库会删掉四张表与那一列，全新库不执行这些语句，两例都通过；DROP 放在 `MIGRATION_STATEMENTS` 末尾，与既有的退役表同一处，`schema_gate` 的版本号随之加一，降级会被拦下。

### 踩坑经验

1. 「谁调用了它」只回答可达性，回答不了「调用之后能不能产出结论」；删一条链之前要把触发条件、执行、落库、读取走完一遍，004 与 005 就是在这里留了尾巴；
2. 退役表的 DROP 一开始放在 `INDEX_STATEMENTS`，升级夹具在版本 63 就因 `calendar_events` 已退役而失败（HEAD 上本来就如此）；放回 `MIGRATION_STATEMENTS` 末尾才与既有先例和 `schema_gate` 一致；
3. 共享工作区里六个语言文件都带着他人改动，且 de / ja / ko / zh-TW 不能无损地 JSON 往返，只能做文本删除；提交时用「HEAD 内容 + 同样的文本删除」生成，而不是挑 hunk；材料文档同理，用「HEAD 文本 + 精确替换」生成，再与工作区逐行比对，补上脚本漏掉的几行；
4. 提交后用 `git archive` 取已提交内容做干净导出再跑测试，才能确认提交没有依赖他人未提交的定义；`tsc` 遇到 JSON 语法错误只报语法错误，他人写到一半的语言文件会让整次结果失效，要等文件恢复后重跑；
5. 局限：没有做浏览器级别的视觉与交互检查（详情页去掉面板后的版本历史布局）；桌面 sidecar 的 SQLite `DROP COLUMN` 沿用 `migrations.py` 里已有的同类写法，没有在桌面包里实测；落后到索引版本 63 之前的古老数据库在 HEAD 上就会失败，这次没有改变这一点；`SKILL_EVOLUTION_ADVANTAGE` 里带日期的测试结果表和 `de/auto-translated-overrides.json` 里已删词条的陈旧条目没有改；整应用入口 `app.main` 在当前工作区因他人未提交的 harness 改动（`agent.security.audit_pack` 缺失）无法导入，没有做整应用启动验证；服务端提交依赖 harness 提交 `e556569995`，harness 发版后要同步锁文件；工作区里其余测试失败来自他人未提交的改动，没有一条指向本次删除的符号。

---

## BUG-AGENT-2026-10-14-010: 词条被超过 100 个页面引用时，面板把截断后的条数当总数展示；详情头部的「链接」快捷入口是硬编码中文且手机上整个消失；窄屏下详情头部把词条名挤到 0 宽

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P3（展示的数量不准、手机上少一个快捷入口；不丢数据） |
| 影响范围 | harness `toolkits/wiki/retrieval/graph_store.py`、`indexer.py`、新增 `concept_links.py`；server `app/api/wiki/router.py` 的 `/wiki/concepts/{name}/links` 响应模型；前端 `wiki/WikiConceptLinksPanel.tsx`、`wiki/WikiConceptDetailPanel.tsx`、新增 `wiki/useConceptHeadingFocus.ts`、`services/wiki/service.ts`、硬编码文案基线 |
| 出现次数 | 1 |
| 关联 | roadmap topic_02 #140 第四批补修；BUG-AGENT-2026-10-14-007 |

### 现象

1. 一个词条被超过 100 个页面引用时，`get_concept_links` 每个方向只返回前 100 条，页签与摘要写「被引用 (100)」，用户会把它当成总数；响应里没有任何「被截断」的标记（合成库 150 个页面引用同一词条，返回 100 条）。
2. 详情头部跳到链接面板的快捷按钮，文案「脉络」与提示「跳转到双向链接与脉络」是硬编码中文，六种语言的用户都看到中文，与面板标题「链接与上下文」叫法也不一致；按钮带 `hidden sm:flex`，手机宽度下整个入口消失。
3. `WikiConceptDetailPanel.tsx` 416 行，超出 400 行预算，且不在行数基线里。
4. 详情头部把词条名、来源徽标、来源对话链接和操作按钮排在同一行且不换行。默认「保存到 Wiki」生成的词条名（`SaveToWikiButton.tsx:92-98`，如 `untitled-note`，111px）查看态下，英、德文案在视口 320 / 360 / 390 / 430 与 1024 的可见宽度都是 0px（视口 768 为 28 / 14px），中文文案在视口 320 / 360 / 390 / 430 / 1024 依次是 0 / 0 / 19 / 59 / 90px，编辑态更窄（英文在视口 1280 也只剩 84px）；这是改前就有的，本批把快捷入口改成常驻图标后窄屏又固定多占 48px。
5. `get_concept_links` 返回 `dict[str, object]`，server 路由用 `res.get("outlinks", [])` 取列表，mypy（server `pyproject.toml` 的 `strict = true`）把它判成不可迭代，`router.py:1482-1483` 是两处真实报错；路由里 5 个带默认值的 `.get`（概念名、两个列表、两个 `*_has_more`）在只有一条返回路径、五个键齐全（`graph_store.py:382-388`）的前提下永远走不到默认值。

### 根因

1. 截断只写在 SQL 的 `LIMIT 100` 里，「是否被截断」没有往上游传。
2. 按钮是直接写的字面量；响应式处理成「窄屏整体隐藏」，而不是「窄屏收成图标」。
3. 小节锚点聚焦（约 95 行：滚动、高亮、多帧重试、同词条内跳转）与展示组件放在同一文件，叠加几次修复后越过预算。
4. 头部是单行 flex，名字是唯一可收缩的项（来源徽标、来源链接、按钮都是 `shrink-0`）。名字自带的 `truncate` 只会把它截成省略号，宽度被挤到 0 时连省略号都没有，所以它不是兜底。
5. 返回值没有类型，键集合与值类型只靠约定；调用方只能用 `.get` 加默认值兜底，类型检查器既核对不了键，也推不出值是列表。

### 修复

1. `get_concept_links` 每个方向多取一行（`LIMIT MAX_CONCEPT_LINKS + 1`，`_fetch_capped`）判断是否还有更多，仍只返回前 100 条，新增 `outlinks_has_more` / `backlinks_has_more`；server 响应模型两个布尔字段（默认 `False`）与前端类型同步；面板在被截断的方向显示「100+」（页签与摘要胶囊），另一方向照常，复用已有的 `{count}` 占位符，六语言没有新增键。不改排序、不加分页（面板没有「加载更多」入口，也没有读取方需要）。
2. 按钮改取已有的 `links.title`；文字按详情头部自身宽度（容器查询 `@xl`，不随视口）显隐，头部较窄时只显示图标并带 `aria-label`，任何宽度都不隐藏；硬编码文案基线里这个文件由 2 收紧到 0，只删这一条。
3. 小节锚点聚焦原样移入 `useConceptHeadingFocus.ts`（115 行；移动的 96 行用脚本与原文逐行比对一致），详情面板降到 330 行。
4. 头部与标题块都 `flex-wrap`：放不下时操作按钮整组换到下一行（`ml-auto` 靠右），标题块里的来源徽标与来源链接再换行，词条名独占一行（标题块 `min-w-0`，名字 `max-w-full truncate`，过长才出省略号）；放得下时仍是一行。头部显式 `space-y-0`：`CardHeader` 基类自带 `space-y-1.5`，不归零时标题块多出 6px 下外边距，单行名字比按钮中心高 3px、换行行距成了 14px 而不是 `gap-y-2` 的 8px；多余的 `justify-between` 去掉（`ml-auto` 已把操作组推到右侧，对布局零影响）。快捷入口文字显隐的容器查询阈值不变（换行之后阈值附近不再有名字宽度的断崖）。
5. `get_concept_links` 返回 TypedDict `ConceptLinks`（新增 `retrieval/concept_links.py`：`ConceptLink`、`ConceptBacklink`，先例是 `pipeline/pending.py` 的 `PendingWikiEdit`），`WikiIndexer.get_concept_links` 同步；server 路由按键直接读取并删掉 5 个 `.get` 默认值，不 import harness 的类型名（类型随返回值推断）。运行时没有变化（TypedDict 就是 dict）。

### 验证

1. 先红后绿：harness 4 例失败（载荷键集合、100 条不截断与 101 条截断、出链方向独立），修复后 `test_concept_links.py` 10 例通过；server 4 例失败，修复后 6 例通过；前端 3 例失败（面板「N+」1 例、快捷按钮 2 例），修复后两个文件 16 例通过。`LIMIT ?` 参数化先单独做，原有 6 例照过，再加红灯。
2. 多取一行是否改变展示哪 100 条：150 条同权重边，上限 100 / 101 / 150 三种取法的前 100 行逐项相同（查询计划是 `idx_wiki_edges_target` 加临时 B 树排序）。这是合成库实测，没有性能声明。
3. 全量：harness `tests/toolkits/wiki` 862 例通过 861，失败 1 例是调用真实 LLM 的 `test_sidecar_integration::test_sidecar_incremental_rebuild_skips_unchanged`（第一次全量停在同文件的另一个用例；整文件单独重跑 3 例通过，当前代码与 HEAD 快照各一次）；server `tests/api/wiki` 与 `tests/integration/wiki`（不含调用真实 LLM 的 `test_wiki_real_llm.py`）164 例通过 161，失败 3 例都在安全拦截用例（`test_wiki_clip_api.py::test_wiki_clip_security_blocked_job_response`、`test_wiki_import_raw_gate.py::test_import_folder_blocks_credential_content`、`test_import_urls_security_blocked`），与链接接口无关，但没有在干净 HEAD 上复跑；前端 wiki `__tests__` 目录 11 个文件 71 例通过（含头部换行与间距类名断言 1 例，先红后绿）。
4. 静态：ruff、mypy（`graph_store.py`）、oxlint、prettier、`verify-i18n` 通过（第一次运行时他人正在改语言文件，报占位符不一致，重跑通过）；`tsc --noEmit` 全量只报他人的 `KanbanTaskHandoffSection.test.tsx` 一条；文件行数门禁不再列出本条改的文件，硬编码文案门禁里这个文件不再出现（整体门禁仍因他人新增的文件失败）。
5. 局限：没有取得真实浏览器证据。`./myrm test -m chrome_e2e …::test_wiki_concept_detail_source_jump` 三次都在 `/settings/wiki` 路由水合超时（`E2E_ROUTE_HYDRATION_TIMEOUT`）：前两次前端日志同期是大量接口请求超时（机器负载均值 38–90）；第三次在头部换行改完之后，运行时与健康检查通过、`/settings/wiki` 返回 200、日志没有编译或运行时报错（负载均值 22–29）。三次都没有走到任何断言，所以既不能证明也不能否定面板在真实浏览器里的表现；该用例验证来源跳转而不是布局，通过了也不覆盖头部换行。为它写的 28 行断言没跑出结果，已撤回。深浅主题没有目测（jsdom 不计算样式），头部换行只有类名断言与下面的副本量测；「100+」只在 harness 层（101 页）与 DOM 层分别验证，没有在真实应用里串起来。
6. 布局实验（独立副本，不是真实应用）：项目自己的 `tailwindcss` 编译加无头 Chromium 渲染。四个版本的类名都由脚本从源文件读出，不是手抄：换行修复前（`97c77ef219`）、换行修复后（`fc0f1475ef`）、只加 `space-y-0`、当前（`f5f8893858`）；头部、标题块、名字、徽标、来源链接、操作组的类名取自各版本的 `WikiConceptDetailPanel.tsx`，再经项目自己的 `cn`（`twMerge` + `clsx`）、`buttonVariants`、`badgeVariants` 合并，所以 `CardHeader` 基类的 `space-y-1.5`、按钮的 `gap-2`、图标的 `mr-2`、保存按钮的 `border-0` 都按真实合并结果带入。头部内容宽由 `SettingsLayout.tsx:322-344`、`WikiConceptsList.tsx:117` 与 `CardHeader` 的 `p-6` 算出（视口 320 / 360 / 390 / 430 / 768 / 1024 / 1280 / 1440 / 1728 对应 238 / 278 / 308 / 348 / 433 / 379 / 550 / 657 / 849px，是公式值，没有在真实页面核对）；文案取 en / zh / zh-TW / ko / de / ja 六种语言的真实值，默认名按 `SaveToWikiButton.tsx:92-98` 的生成规则取 `untitled-note`（111px）与 `rag-evaluation-metho`（184px），再加一个 40 字符长名（356px）。每个版本 6 语言 × 9 视口 × 3 名字 × 查看 / 编辑态 = 324 个组合。词条名完整可见（长名按拿到整行宽度算）的组合每格 54 个：换行修复前 `untitled-note` 查看 / 编辑态 21 / 17、`rag-evaluation-metho` 14 / 14、长名 4 / 5，其中名字被压到 0px 的每个名字 45 / 108；换行修复后与当前版本全部 54 / 54。当前版本与「只加 `space-y-0`」版本在 324 个组合里的操作组位置、宽度、头部高度、名字宽度逐项相同，即 `justify-between` 零影响；当前版本与换行修复后版本的换行判定 324 / 324 一致（都是 249 个换行），徽标、来源链接、操作组宽度逐项相同。间距的差别：`space-y-1.5` 被 Tailwind 4.3.3 编译为 `:where(.space-y-1.5 > :not(:last-child)) { margin-block-end: 6px }`，落在标题块上，一行的 75 个组合里名字中心比按钮中心高 3px，换行的 249 个组合里标题块与操作组相距 14px；加 `space-y-0` 后分别是 0px 与 8px（`gap-y-2`）。头部高度：一行 67 → 65px，换行 107 / 127 / 133 / 153 → 101 / 121 / 127 / 147px。代价是放不下时头部变高：当前版本里视口 1280 的查看态 `rag-evaluation-metho` 在英、德文案换行（65 → 101px），编辑态更早，`untitled-note` 的英、德就换行；视口 1440 的查看态德语 `untitled-note` 与英、德 `rag-evaluation-metho` 换行；视口 1024 的所有语言默认名都换行，视口 1728 的两个默认名全部一行；40 字符长名 108 个组合里 99 个换行。控件宽度（en / zh / zh-TW / ko / de / ja）：徽标（`chat-compound`）117.4 / 68.1 / 68.1 / 66.7 / 104.9 / 92.2px，来源链接 115.5 / 47.7 / 47.7 / 44.9 / 101.2 / 47.5px，查看态操作组（快捷入口只显示图标时）128.5 / 129.0 / 129.0 / 126.8 / 168.8 / 129.0px，视口 1440 起快捷入口显示文字，该组变为 236.2 / 204.1 / 192.6 / 188.0 / 336.0 / 205.2px，编辑态操作组 189.4 / 168.1 / 168.1 / 163.5 / 243.6 / 204.0px。最宽的德语编辑态 243.6px 对视口 360 的行宽 278px 有 34.4px 余量，对视口 390 有 64.4px；视口 320 行宽 238px，该组超出 5.6px，落在 24px 右侧内边距里；换行修复前同一组合超出 33.6px，比内边距多 9.6px，面板 `Card` 带 `overflow-hidden`，按几何关系保存按钮右侧会被裁掉（副本没有套 `Card`，未渲染验证）。副本用 system-ui 字体与默认主题，图标是同尺寸的占位 SVG，不含产品字体（Inter，用户还能换字体）与主题配色。探针脚本是一次性临时文件，没有入库，这些数字不能在仓库里一键复现，也没有在真实浏览器里校准。
7. 类型与回归：server `router.py` 的 mypy 从 11 个错误降到 9 个，消失的正是 `:1482-1483` 两处，没有新增；剩下 9 个（`:617`、`:829`、`:1780`、`:1781`、`:1852`、`:2238` 两个、`:2395`、`:2445`）在 health、queue、pending、graph 等其他端点，与本条无关，未改。harness 的 mypy（`graph_store.py`、`indexer.py`、`concept_links.py`）、ruff check 与 format 通过，`graph_store.py` 388 行；`test_concept_links.py`、`test_link_edges.py`、`test_wiki_alias_and_chinese_anchor.py`、`test_concept_identity.py` 共 42 例通过，`tests/toolkits/wiki` 全量（不含调用真实 LLM 的 `test_sidecar_integration.py`）859 例通过；server `test_wiki_concept_links.py` 与 `test_wiki_concept_links_integration.py` 6 例通过，`router.py` 的 ruff 通过。改前先在沙箱里用与 `router.py` 相同的 pydantic 模型复现了同样的两个报错，TypedDict 写法下为 0。

### 踩坑经验

1. 「LIMIT N」会静默丢数据，调用方没法知道；在查询处多取一行当探针，返回前 N 条加一个布尔，比让前端猜成本低得多。换成 N+1 后前 N 行是否不变要验证，并列权重下尤其如此。
2. `check-hardcoded-copy.mjs --write-baseline` 会把所有已降低的文件一起收紧，共享工作区里会连带改到他人的条目；这里手工只删自己的那一行，再确认差异只有一行。
3. 「窄屏隐藏」会把入口直接拿掉；入口比文字更重要时，应该收成图标并补 `aria-label`。
4. 文件刚过预算时，往里加一行就会让门禁里多一个未入基线的文件；提取一段内聚的逻辑（这里是锚点聚焦 hook）并逐行比对，比删注释压行数稳妥。
5. 共享的 e2e 基础设施会被他人同时改：第一次运行时 `scripts/dev/ready.sh` 正在被编辑、有语法错误，第二次起能解析；之后两次的路由水合超时与代码无关，但也因此拿不到浏览器证据，不能把「没有失败」写成「验证过」。
6. 组件库基类会悄悄带来布局间距：`CardHeader` 自带 `space-y-1.5`，改成 `flex-row` 后仍对标题块生效（Tailwind 4 编译为 `:not(:last-child)` 的下外边距），表现为 3px 错位和换行行距变大；改布局后要用项目的 `cn` 合并出真实类名再量。手算控件宽度也会错（漏 `font-medium`、按钮内部 `gap-2`、图标 `mr-2`、保存按钮的 `border-0`），宽度要从真实类名量出来。

---

## BUG-AGENT-2026-10-14-011: 悬停显现的菜单触发器在菜单打开时消失；Kanban 卡片与待办记忆勾选框只能鼠标悬停才出现；棘轮基线写入命令会放宽额度；11 个高密度组件的界面文案写死在源码里

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（键盘与触屏用户够不到卡片动作；非中文用户在 11 个组件里看到未翻译或中英混排的界面；不影响数据） |
| 影响范围 | 前端 `scripts/`（`run-lint-gates.ts`、`reveal-contract-scan.ts`、`ratchet-baseline.ts`、`check-a11y-ratchet.mjs`、`check-hardcoded-copy.mjs`、`source-files.mjs`）、`lib/utils/a11y.ts`、`kanban`、`memory/cards`、11 个组件及 6 个 `locales/*.json` |
| 出现次数 | 1 |
| 关联 | 提交 `d3dad2bd6`、`00647c949`、`e80ea3ed3`、`48695d574`、`658566e7b`、`f3b7ef162`、`dd8a64b12`，后续批次 `65874ad322`、`53aa05eada`、`3af4e8f772`、`43b82f2614`、`7a64855249`、`ac36e37f94`，本地提交，未 push；接续条目 006 的「局限」 |

### 现象

1. `bun run lint` 用 `&&` 串联各门禁，前一个变红后面的就不跑：硬编码文案门禁在 `verify:a11y` 红着的那段时间没有在 CI 里执行过；
2. Kanban 卡片的 Specify / Decompose / Move / Reclaim / Delete 只在鼠标悬停时才渲染，键盘与触屏够不到；卡片详情抽屉只能双击打开；dnd-kit 在卡片内任一按钮上按 Enter / Space 都会启动键盘拖拽；待办记忆的勾选框由 JS 悬停状态控制；
3. 悬停显现的控件没有门禁：`opacity-0 group-hover:opacity-100` 的控件键盘聚焦时看不见、触屏上不存在，jsx-a11y 与单测都看不到；
4. `--write-baseline`（硬编码文案）与 `--ratchet`（a11y）用当前数字覆盖基线，失败信息推荐的命令本身就能把退化改绿；
5. 用 `REVEAL_ON_HOVER` 显现的菜单触发器，菜单打开后指针与焦点进入 Radix 的 portal，`group-hover` 与 `group-focus-within` 同时失效，触发器在自己打开的菜单下面淡出；
6. 子任务详情抽屉 / 视口 / 洞察、风险确认卡、会话导入、模型单价浮层、压缩锚点条、偏好雷达、Focus 清空按钮、循环状态条、凭证暂存卡共 11 个组件的标签、提示、`aria-label`、toast、校验错误是字面量，门禁基线记 132 处。

### 根因

1. 门禁聚合用 shell 串联，没有「全部跑完再汇总」的步骤；
2. 悬停显现只靠样式类约定，没有机器校验「键盘路径 + 触屏路径」；
3. 基线写入命令的语义是「覆盖」而不是「收紧」；
4. `data-[state=open]` 没有进入显现常量，浮层打开状态没有被当作显现条件；
5. 文案进 locales 靠人工，扫描器只统计直接写在 JSX 里的字面量，toast、校验函数返回值、选项常量里的文案既不在门禁里，也不在基线里。

### 修复

1. A `d3dad2bd6`：`scripts/run-lint-gates.ts` 逐个执行 `LINT_GATES` 并汇总退出码，本地与 CI 共用同一份清单；
2. C `00647c949`：卡片动作收进一个常驻挂载、悬停 / 键盘聚焦 / 触屏都可显现的菜单，并补「任务详情」入口；卡片本身注册为 dnd-kit 的 activator，内部按钮在键盘上不再触发拖拽；记忆勾选框改用同一显现契约并补可访问名称；
3. D `e80ea3ed3`：`reveal-contract-scan.ts` 零容忍扫描「悬停显现却缺键盘路径或触屏路径」的交互元素，与键盘焦点可见性一起在 a11y 门禁里一次列全；目录遍历统一用 `source-files.mjs`，豁免计数通过 `includeTests` 继续覆盖测试文件；
4. B `48695d574`：`ratchet-baseline.ts` 的 `tightenCounts` 逐项取 `min(当前, 基线)`，不新增条目、不放宽额度，两个基线写入命令与提示信息同步；
5. E `658566e7b`：`REVEAL_ON_HOVER` 增加 `data-[state=open]:opacity-100`；
6. F `f3b7ef162`：11 个组件的全部用户可见字符串迁入 `locales/{en,zh,zh-TW,de,ja,ko}.json`，新增 189 条键；已存在的键（`chat.loopScheduler.*`、`commands.builtin.focus*`、导入结果文案）直接复用，并删掉它们前面永不触发的 `|| '中文兜底'`；雷达预设与维度改为携带翻译键，凭证校验函数改为返回错误码；Focus 清空确认里的加粗用 `t.rich`；顺带给雷达关闭、密钥显示 / 隐藏、凭证行删除、抽屉复制这几个纯图标按钮补了可访问名称，修掉 `ModelPricingPopover` 的 `curly` 告警；基线按这 11 个文件精确收紧 132 处；
7. `dd8a64b12`：修正 C 里 `KanbanDndComponents.keyboard.test.tsx` 的不稳定 `next-intl` mock（`verify:stable-mocks` 硬门禁拦截）；
8. 本条目所在提交：`SubagentInsightsView` 的异常行由 `div role="button"` 改为原生 `button`，其中的类型徽章改用 `badgeVariants` 的 `span`（`Badge` 渲染 `div`，放进 `button` 是无效嵌套），`prefer-tag-over-role` 基线 72 → 71。

### 验证

1. C 在真实 Chrome 里对真实的 `KanbanDropColumn` 验证；E 在真实 Chrome 里用生产常量验证——指针停在已打开的菜单内时触发器 opacity 保持 1（修复前为 0）；D 在干净 HEAD 导出上通过、注入违规写法后失败，并做了变异测试；B 在干净导出上端到端验证基线只降不升；
2. F 的 6 种语言全部过 `verify:i18n` 的键对齐、占位符、术语与禁用词检查（过程中修掉 de 的 4 处翻译壳与 zh-TW 的 1 处禁用词）；`verify-i18n-references` 通过（2459 个文件无缺失键）；
3. 测试里 `next-intl` 被全局 mock 成 `key => key`，ICU 语法错误测不出来，所以另用真实 `createTranslator` 把 189 条键 × 6 种语言共 1134 次渲染跑了一遍：无 `INVALID_MESSAGE`、无缺失键、无残留花括号或标签；反例对照（故意写坏的消息）能被检出；动态键（雷达 13 个、TTL 4 个、子任务状态 12 个）逐一核对存在；
4. 在已提交树的导出上跑 `bun run lint` 的 5 个门禁全绿、fractal docs 通过、prettier 通过；工作区 vitest（chat-window / sidebar / risk-approval / approval / chat / message-input-actions / kanban / scripts）198 个文件 1143 例通过；全量 `tsc --noEmit` 只剩他人未提交的 `KanbanTaskHandoffSection.test.tsx(68,3)`，我改的文件 0 报错；
5. 新增或补充约 31 个用例，包含此前没有测试的 `FocusFlushButton`、`SessionImportModal`、`ModelPricingPopover`、`SubagentInsightsView`。

### 踩坑经验

1. 扫描器计数为 0 不等于没有硬编码：`MaskedCredentialInputCard` 扫描器只报 8 处，实际有 31 条用户可见字符串（toast、校验返回值、下拉选项都不在扫描范围）；迁移时按文件逐条核对，而不是只清到门禁变绿；
2. C 提交时只跑了这个测试本身，没有在已提交树的导出里跑完整 lint 链，漏掉 `verify:stable-mocks`，F 做导出核对时才发现；提交前要在导出上跑整条链，而不是只跑自己新增的测试；
3. 共享工作区里 locales 被他人改动了上千行：用「在 HEAD 文本上按命名空间文本插入」生成提交用的 blob，再对同一份插入逻辑在工作区文本上重放，两边都用「解析后等于改前 + 我的键」自检；
4. 翻译壳检测会拦下与英文完全相同的值：de 的 `Subagent`、`Live`、`Tools ({count})`、`Commits ({count})` 都得换成真正的德语写法或项目里已有的写法；
5. 局限：新增的 de / ja / ko / zh-TW 译文只经过机器门禁，没有母语者审校；真实聊天页与 Kanban 页没有端到端点过（后端 :8000 未启动）；鼠标 + 触屏并存的混合设备没有覆盖；`SubagentDetailDrawer.tsx` 591 行（改前 574）、`MaskedCredentialInputCard.tsx` 463 行，未拆分；`LoopStatusBar` 的时长缩写 `m` / `s` 与服务端给的 `current_delay_human` 仍是英文；`RiskConfirmationCard` 发给后端的审批理由是英文审计串，保持不变；干净 HEAD 上 `verify:i18n` 本来就是红的（ja / ko / de / zh-TW 各缺 92 个 en 键、17 个孤儿键、de 的 `settings.browserDoctor.statusOptional` 是翻译壳），`verify:orphans` 同样为红，均不是本次引入；扫描器的覆盖面限制见条目 006，存量只是继续下降（当前 3408 处 / 358 个文件），没有清零。


### 补充：同一天的第二批（ICU 门禁、toast 门禁、Kanban 确认、MCP 文案）

上面「局限」里「扫描器只覆盖 JSX 字面量、toast 不在门禁里」对 toast 不再成立（B 的门禁已覆盖）；「Kanban 页没有端到端点过」仍然成立，见下面的验证。

**现象**

7. `locales/*.json` 有 17 条文案不是合法 ICU（`{{secret:KEY}}`、裸 `<token>` 等）：开发构建抛 `INVALID_MESSAGE`，生产构建带插值参数时把键路径显示给用户；没有任何门禁检查 ICU 语法（A，`65874ad322`）；
8. 约 150 处 toast 写死中文或英文，分布在 store、hooks、services 与组件里（B，`53aa05eada`）；`t('key') || '兜底'` 的兜底永远不会执行：next-intl 对缺失或解析失败的键返回带命名空间的键路径，不返回空值；
9. Kanban 卡片菜单与拖拽浮层里「删除」「回收」一次点击就执行（C，`43b82f2614`）：删除连同运行记录与事件一并清除，并把依赖它、其余依赖都已满足的 backlog 任务提升为就绪（`app/services/kanban/task_ops.py:230-251`，级联见 `app/database/models/kanban.py`）；回收会停掉执行中的 Agent 并重置为就绪（`move_orchestrator.py:291-321`）；
10. 共享的 `ConfirmDialog` 在受控且没有 trigger 时，关闭后焦点落到 `<body>`，键盘用户回到页面顶部（C）；
11. MCP 扫描发出的 `dangerous_env_injection` 在 `settings.mcpThreat` / `mcpThreatRec` 里没有文案；`localizedOrFallback` 用「返回值等于键」判断有没有译文，而 next-intl 返回的是 `settings.mcpThreat.x`，永远不相等，用户看到键路径而不是服务端原文（G，`7a64855249`）；
12. zh-TW 有 7 条把「歷史」写成「曆史」（D，`ac36e37f94`）。

**根因**

1. ICU 语法与 toast 文案都没有门禁，而 toast 弹在事件处理里，tsc 与单测都看不到；
2. `|| '兜底'` 依赖「缺键返回空值」这个不成立的假设；`localizedOrFallback` 的判断同出一源；
3. 删除 / 回收的入口直接调用执行函数，中间没有确认层；
4. Radix 受控 `AlertDialog` 没有 trigger 时，关闭没有可还焦点的元素。

**修复**

1. A：`check-icu-syntax.mjs` + `icu-syntax-scan.ts`（用 `@formatjs/icu-messageformat-parser` 解析每条文案，零容忍）进入 `LINT_GATES`，并修掉 17 条非法文案；
2. B：toast 文案迁入 locales（新增 69 个键 × 6 语言）：组件用 `useTranslations`，store / 工具函数用 `showI18nToast` / `translateI18nKey`；`3af4e8f772` 加 `toast-copy-scan.ts` 并入 `check-hardcoded-copy.mjs`——`.ts` / `.tsx` 里的 toast 写死文案零容忍、没有基线，`verify-i18n-references.mjs` 同时校验 `translateI18nKey` 的键；
3. C：看板视图持有一个 `ConfirmDialog`（`KanbanTaskActionConfirm.tsx`），卡片菜单只发起请求；文案交代后果；`kanban.reclaimConfirm` 实为菜单标签，改名 `reclaimAction`；共享 `ConfirmDialog` 在打开时记下焦点元素（焦点在菜单项上时改记菜单的触发按钮），关闭后还焦点，已有的 force-promote 与 drop-confirm 对话框一并受益；
4. G：`localizedOrFallback` 改用 `t.has(key)`，补 `dangerous_env_injection` 的描述与建议 × 6 语言；
5. D：zh-TW 7 处「曆史」改「歷史」。

**验证**

1. A、B、C、G 与门禁提交各在干净导出上跑过 `bun run lint`、相关 vitest、全量 `tsc --noEmit`（只剩 `clipNotifyPayload.test.ts` 的导出产物）；B、C、G 与门禁提交另跑了 `check_fractal_docs`，B、G 与门禁提交另跑了 `verify-i18n-references`（均通过）；测试规模：B 618 个测试文件 / 4445 例，C 83 / 694，G 139 / 1103，门禁 12 个脚本测试文件 / 122 例；D 只改 zh-TW 文案，只跑了 `verify:i18n`，输出与 HEAD 逐字一致（G 同样一致）；
2. 变异检查：向干净导出注入 `{{count}}`，ICU 门禁退出码 1 并报 `MALFORMED_ARGUMENT`；注入硬编码 toast、`t() || 'x'`、`err.message || '…'`、模板字符串四种写法，toast 门禁全部失败并列出行号，错误的 `translateI18nKey` 键被引用校验报出；G 的「无译文时显示服务端原文」用例在旧比较下失败；撤销 `ConfirmDialog` 的焦点修复后，C 的焦点用例失败；
3. toast 门禁扫描 2432 个源码文件（不含测试与 `.d.ts`），两组各 3 次实测：2.8–5.0 秒、3.5–6.0 秒（后一组测量时机器负载约 50）；
4. C 的组件测试用真实 Radix 与真实 next-intl（6 语言文案），25 例；**Kanban 页没有在真实浏览器里验证**：共享 :3000 与我单独起的 :3300 两个开发服务器上，无头 Chromium 都停在设置页骨架，页面反复重新导航，从未渲染到看板；源码里有 `GlobalErrorBoundary` 等自动 `location.reload()` 的路径，当时机器负载 60 以上、分块请求长时间挂起，但没有确认是哪条路径触发的，也没有确证是负载所致。375px 宽的德语长文案是否折行、两套主题下对话框配色，因此没有看过实际渲染。

**局限**

1. 门禁盲区：先赋给变量再传入 toast 的文案、经其它封装函数转发的 toast；
2. 存量：工作区非测试源码里 `t('…') || '字面量'` 形态仍有 315 处 / 65 个文件（`rg --pcre2 "\bt\(\s*['\"][^)]*\)\s*\|\|\s*['\"]" src` 去掉测试文件）；toast 里的已由门禁清零，其余位置没有处理；18 个文件用了 next-intl 会忽略的 `defaultMessage`；9 个文件用 `isZh ?` 三元；`clipboardUtils.ts` 的 `ask()` / `window.confirm` 文案与 `api.ts:644` 的 `console.warn('重试失败:')` 仍是中文字面量；
3. HEAD 上 `verify:hardcoded-copy` 为红，原因不是这批改动：他人提交的组件（workspace-boundary、visual-diff 审批卡等）顶破 JSX 棘轮基线，已提交的 `TimeTravelRollbackModal.tsx` 仍有 10 处 toast 字面量（其作者的工作区版本已迁移、尚未提交）；`verify:i18n` 在 HEAD 上本来就是红的（各语言缺键 / 孤儿键）；
4. 新增的 de / ja / ko / zh-TW 译文只经过机器门禁，没有母语者审校；
5. 删除仍是永久删除，没有回收站；`KanbanBoardView.tsx` 已 981 行（超过 500 行上限，本批只加了确认接线的 +19 / -4 行，未拆分）。

---

## BUG-AGENT-2026-10-14-012: 技能演进审批卡上的「变更预测与归因」永远自证为真；「测试通过」其实是质量分大于 0；回归闸门把原版就过不了的断言算成每个候选的固定扣分；沙盒校验给无可执行内容的技能盖「已验证」

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（审批人据以放行的几个数字不是测出来的：预测归因恒为「已证实」、扫描 / 测试徽章与实际检查不符、自动合并的「大改动」信号漏掉同长度重写；没有数据损坏） |
| 影响范围 | harness `agent/skills/evolution/core/`（`change_manifest`、`eval_regression`、`proposal_builder`、`types`）、`agent/skills/evolution/execution/sandbox_validator.py`、`eval/`（`manifest_prediction`、`metric_contract`、`leakage_guard`）、`api/__init__.py`、`install_guard/_generated/core_ip_manifest.py`；服务端 `app/api/skills/{evolution/pending,growth}.py`、`app/services/skills/{evolution_review,growth}/`、`app/services/agent/{confidence_approval_flow,evolution/skill_immune_service}.py`、`app/services/skills/draft_notification.py`、`app/database/{models/skill,migrations}.py`；前端 `growth/`、`skills/SkillGrowthCaseCard`、`PendingEvolutionsDashboard`、`SkillHistoryPanel`、`services/skill/growth.ts`、六种语言文案；根仓库优势材料 |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-14-009`（009 的「保留不动」里的变更清单 `build_change_manifest` 这次核实后一并删除，审批卡的 `testPassed` / `verificationProof` 改为只陈述真实发生过的检查）；提交 harness `645607acb1`、服务端 `d2a7e27b3f`、前端 `c82ad4528e`；扫描结论的后续修正为服务端 `f294b28648`、前端 `7fc37377fe`；均为本地提交，未 push |

### 现象

1. 提案卡的「变更清单预测」段把预测通过率与「实测」通过率并排展示，并给出 CONFIRMED / REFUTED / REGRESSION 归因。「实测」是同一个静态断言函数在同一段文本上再跑一遍，与预测同源，删掉一个必需步骤的重写也被判为已证实；指标守卫读取 `predicted_value` 键，而清单从来不写这个键，这条链永远为空；
2. `test_passed` 在自动流里取 `proposal.score > 0`，卡片上显示为「测试通过」，但演进流程里没有任何测试执行；运行期免疫闸门拦下的记录（没有跑过任何扫描）被标成 `FAILED_SCAN`，语言文案写「Failed Scan / 扫描失败」；人工修订路径里扫描器抛异常时被按「通过」记录；卡片上另有读取扫描摘要的安全徽章，它以 `TRUSTED` / `UNTRUSTED` 这类内部枚举的大写原文显示，提示文字是写死的英文；
3. 回归闸门对每个断言都做全局扣分：原版就过不了的断言（例如对 Markdown SOP 写的 Python AST 断言）让所有候选都被扣同一个常数；候选丢掉全部用例时的硬过滤，在少于七个用例时被扣分算术挡住而不可达；
4. `SandboxValidator` 对纯提示词或只有 bash 的技能返回 `is_verified=True`；ZIP 导入闸门把只有示例代码、没有断言的代码块判为 `Hollow Test Rejected`；
5. 自动合并的「大改动」信号只比较长度：同长度的整段重写差值为 0，不触发；
6. `pending_evolutions` 表与模型没有任何路由或页面读写（提案走 `approval_records`）。

### 根因

1. 清单预测把「预测」和「验证」做成了同一函数的两次调用，没有独立的验证来源，因此无法被证伪；
2. `test_passed` 沿用了早期「提案先跑测试」的设想，字段名与取值没有随流程变化；状态枚举与文案没有随运行期免疫闸门这个新来源更新；
3. 回归闸门没有区分「原版本来就过 / 本来就过不了」，把后者也当成必须守住的基线；
4. 沙盒校验把「没有发现失败」等同于「已验证」；
5. 长度差是最容易写的近似，量的是「变长了多少」而不是「改了多少」。

### 修复

1. W1 + W2（删除）：harness 删除 `change_manifest`、`eval.manifest_prediction`、`eval.metric_contract`、`evaluate_pareto_generalization` 及其导出与 `core_ip_manifest` 条目，`ProposalBuilder` 不再生成清单；服务端删除清单归因路由与重建、载荷 / 查询 / 卡片类型里的清单与归因字段、`proxy_guard` 一整条代理对齐链；前端删除 `ManifestPredictionsPanel`、卡片里的预测段与对应服务类型；历史审批记录里残留的旧键由 pydantic 默认的 `extra=ignore` 忽略（有加载测试）；
2. W3 真实性：`test_passed` 的含义收窄为「该内容的安全扫描没有发现问题」——自动流里取扫描摘要的 `total_findings == 0`（扫描只拒绝 critical，到审核的提案仍可带 high / medium 发现，摘要存在不等于干净），没有摘要为 `None`；人工修订路径取 `is_clean`，扫描器抛异常为 `None`，并把 `security_scan_summary` 刷新为修订后内容的扫描结果（扫描器不可用则清空，不再保留修订前内容的摘要）；运行期免疫记录、AST 失败的零分提案都是 `None`。卡片不再单设「扫描通过 / 未通过」徽章：扫描结论只由读取摘要的安全徽章表达，该徽章改用「低风险 / 中等风险 / 高风险 / 已拦截」措辞与本地化提示（六种语言），成长案例接口与前端摘要类型不再携带 `test_passed`；修订提示只把 `=== false` 当成扫描未通过；`FAILED_SCAN` 的六种语言文案改为中性的「检查未通过 / Check Failed」；沙盒校验在没有实际检查时返回无证明，提示词类技能不再盖「已验证」，只有带断言的代码块才可能被判空洞，导入闸门语义不变；删除 `pending_evolutions` 模型，在 `MIGRATION_STATEMENTS` 末尾追加 `DROP TABLE IF EXISTS pending_evolutions`；
3. W4：回归闸门只守住原版通过的用例，扣分按「丢失的受守用例数」计算（每个 0.15、上限 1.0），候选丢光全部受守用例才硬过滤；原版就过不了的断言不再产生扣分；
4. W5：`confidence_approval_flow` 的大改动信号改为按字符 3-gram 多重集比较的「改动占比」（线性时间），同长度的整段重写占比接近 100%，会触发，整段追加仍会触发，阈值仍是 50%；顺手去掉对 dataclass 字段的 `getattr`；
5. 文档：两处 `_ARCH`、`ARCHITECTURE`、`SKILLS_SYSTEM`、前端 `_ARCH` 与根仓库优势材料里关于清单预测、帕累托、归因的说法改成代码事实。

### 验证

1. harness（提交 `645607acb1`）：`tests/agent/skills/evolution` 与 `tests/eval` 共 712 通过；回归闸门新增基线相对用例，沙盒校验新增「无证明」与「空洞判定」用例；
2. 服务端：`tests/api/evolution`、`tests/api/skills`（不含他人的 `test_curator.py`）、`tests/services/skills`、`test_skill_immune_service`、新增的 `test_pending_evolutions_table_retired`（升级库与全新库各一例）共 381 通过、1 跳过；`ruff check` / `ruff format --check` / `pyright` 对 22 个改动文件 0 告警；
3. 前端：技能 / 成长 / 服务相关 31 个测试文件 206 例通过（新增 `SkillGrowthCaseCard.securityIndicator.test.tsx`：四个信任等级都显示风险措辞与本地化提示、不出现大写枚举原文，未知等级只显示分数，无摘要不显示徽章，被拦截状态的标签不含 scan 字样）；`oxlint` 对改动文件无告警；`verify-i18n` 六种语言通过；`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx(68,3)`；
4. 改动占比的度量对比：`difflib.SequenceMatcher` 在 2000 行半空行文本上（`autojunk=False`）超过 8 秒，在 2 万行互不相同的文本上（`autojunk=True`）仍超过 8 秒；3-gram 多重集比较在同样的 2000 行输入上 7 毫秒、2 万行（53 万字符）输入上 129 毫秒（本机单次实测）；
5. 已提交内容的干净导出（`git archive HEAD`，补上未入库的 `.env.test`、`e2e_core`、`shared/config`）：服务端 `tests/api/evolution`、`tests/api/skills`、`tests/services/skills`、`tests/database` 共 512 通过、1 跳过（含 `test_curator.py`，在干净导出里全部通过）；前端技能 / 成长 / 服务相关 28 个测试文件 191 例通过；导出里 `verify-i18n` 仍是红的，是 HEAD 上本来就有的「ja / ko / de / zh-TW 各缺 92 个 en 键、17 个孤儿键」，在本次提交之前的 `7a64855249` 上同样如此，输出里没有出现本次涉及的任何键；
6. `server_harness_import_baseline.txt` 里 `manifest_prediction` 与 `eval_regression` 两条已不再被服务端导入，随之删除，`test_baseline_matches_current_imports` 的「基线多出」一侧清空（该测试剩余的差异全是他人新增的 harness 模块导入）。

### 踩坑经验

1. 「预测 vs 实测」只有在两边来自不同来源时才有意义；同一函数在同一输入上调两次，只是在展示一个恒等式；
2. 字段名叫 `test_passed`，含义却早已变成别的东西，比删字段更危险：下游的徽章、提示、导出都在按原名解释它；这次保留字段名（避免一次牵动 API 与历史记录），只收窄语义并让「没检查过」可以表达为 `None`；
3. 度量改动幅度时，序列对齐类算法在重复文本上会退化到不可用，且对没有空白的中文与单行描述没有意义；字符 n-gram 多重集线性、对两类文本都稳定；
4. 一次删除要沿「入口 → 计算 → 落库 → 展示」走完：删掉 `evolution.core.eval_regression` 的服务端导入后，架构基线里对应的行同时变成过期项；
5. 徽章上的结论必须能由同一份证据推出：首版把「有扫描摘要」记为 `test_passed=True` 并配「安全扫描通过」徽章，自检时发现扫描只拒绝 critical，带 high 发现的提案照样进入审核甚至自动合并，卡片上「通过」徽章会和旁边显示高风险的安全徽章互相矛盾；同一张卡上出现两个口径的扫描结论，删掉多余的那个，比把两个调到一致更稳；修订路径同样如此：它只更新布尔值而不刷新摘要，安全徽章会一直显示修订前内容的扫描结果；
6. 局限：没有取得浏览器级别的视觉检查（卡片去掉预测段后的布局、安全徽章新措辞在深浅主题下的显示）；人工修订路径把任何发现都判为扫描未通过，自动流只拒绝 critical，两条路径的严格程度不同，没有统一；发现详情面板仍显示 `threat_type` 原始标识与扫描器的英文描述；`DROP TABLE` 只覆盖升级库与全新库的两个夹具，没有在桌面包里实测；`tests/architecture` 仍有他人未提交改动造成的失败（路由消费者、API 服务词汇、包初始化、前端 API 路径、harness 导入基线的新增项），没有一条指向本次删除的符号；`tests/api/skills/test_curator.py` 的 4 例失败来自他人未提交的 `curator/service.py`；新增的 de / ja / ko / zh-TW 译文只经过机器门禁；服务端提交依赖 harness 提交 `645607acb1`，harness 发版后要同步锁文件。

---

## BUG-AGENT-2026-10-14-013: 技能库满载后删除技能也不会恢复自动学习，满载提示发给了没人连接的 WebSocket；待审核页的容量条自己写死 50 条；版本历史把内部标识原样印给用户；影子 A/B 删除后公开文档、路线图与官网仍在宣称它

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（技能库满载后用户删掉技能也不会恢复自动学习，且全程没有任何提示；公开材料仍在宣称已删除的验证闸门；不影响数据） |
| 影响范围 | harness `agent/skills/evolution/core/budget_governor.py`、`agent/skills/evolution/db/store_queries.py`；服务端 `app/services/agent/evolution/engine.py`、`app/services/skills/evolution_events.py`、`app/services/event/app_event_bus.py`、`app/api/router.py`（删除 `app/api/skills/ws_evolution.py`、`app/services/skills/ws_hub.py`）；前端 `hooks/globalEvents/`、`lib/skills/versionOrigin.ts`、`PendingEvolutionsDashboard`、`SkillVersionsPanel`、六种语言文案；品牌仓库的公开文档与官网文案；根仓库优势材料与路线图 |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-14-009`（影子 A/B 整条链的删除；本条补齐它遗留的容量规则、公开文档、官网与路线图表述）、`BUG-AGENT-2026-10-14-012`；提交 harness `d46a104e1`、myrm-agent `dcdf55a512` / `00ac99ccf3` / `ef6148e871`、品牌仓库 `a40d61da`、根仓库 `c67375633`，本地提交，未 push |

### 现象

1. 技能库达到上限后自动学习会暂停，但用户删除或归档技能并不能解除：容量按进化库 `skills.db` 里的记录计算，而删除、归档只动安装目录，从不触碰进化库，所以库会一直满着；
2. 满载提示是向 `/ws/evolution` 广播的，前端、桌面端与扩展里没有任何代码连接这个地址（旧提交里前端只有发布、语音、浏览器录制三类 `new WebSocket`），用户从头到尾看不到「已暂停」；
3. 每个满足触发条件的对话回合，都会把进化库里所有技能正文逐个计 token，再与 40,000 token 的上限、80% 软阈值比较；技能正文按需加载、并不进系统提示，这个上限与提示词成本无关；容量检查失败时只记 debug 日志；
4. 待审核页的容量条把上限写死为 50，计数用的是本地技能列表长度，与服务端判定用的不是同一个集合；
5. 版本历史每一行把服务端写入的 `created_by` 原样印出来（`agent_meta_tool`、`evolution_engine`、`batch_import`），`createdByLlm` 的文案还写着「LLM 优化」；
6. 影子 A/B 链删除后，公开的技能演进文档（英 / 中 / 韩）仍把「A/B 测试」列为安全层，竞品对比页对技能库容量的描述与代码不符，官网评价文案、内部优势材料和路线图里也还有已不存在的说法。

### 根因

1. 容量规则同时按条数与 token 计量，数据源是进化库而不是用户当前看得到、删得掉的技能集合，删除与归档没有回写进化库；
2. 满载提示沿用了 WebSocket 中枢推送，加推送时没有核实有没有订阅端；
3. 把 token 上限当成「提示词预算」，但技能正文按需加载，上限量的是另一件事，却每回合付出全量分词的代价；
4. 前端自己画了一个容量条，常量与计数口径都与服务端各算各的；
5. 展示层直接取了存储字段；
6. 删除一条链时只清了代码，没有把公开文档、官网、路线图当成同一次删除的一部分。

### 修复

1. harness `d46a104e1`：`SkillBudgetGovernor.check_budget(evolution_type, current_count)` 改为纯函数，只按数量（默认上限 50）判定，修复类进化（FIX / OPTIMIZE_DESCRIPTION）不受限；删除 token 上限、软阈值、冷技能识别与 `cold_storage_days`；`store_queries` 新增 `count_active_skills`（`COUNT(*)`，与读取活跃技能共用同一个过滤条件）；
2. 服务端 `dcdf55a512`：`check_skill_budget_before_evolution` 先用 `COUNT(*)` 取数，只有达到上限时才对照实际已安装且未归档的技能（`describe_skill_lifecycle`）核对一次，所以删除、归档后会自动恢复学习；存储不可读时放行并记 WARNING；满载时对该 agent 作用域只发布一次 `SKILL_CAPACITY_REACHED`（全局 SSE），容量释放后再次填满才会重新提示；删除没有订阅端的 `/ws/evolution` 与 `ws_hub`，进化触发与运行时里的 ws 推送一并去掉；
3. 前端 `dcdf55a512`：新增 `hooks/globalEvents/skillCapacityToast.ts`，收到事件弹一条可替换的本地化 toast（只展示上限数量，不展示服务端措辞与 agent 标识），操作直达「技能管理」；删除待审核页的容量徽标与横幅；六种语言补 `notifications.skillCapacityReached` / `skillCapacityReachedHint` / `manageSkills`；
4. 前端 `00ac99ccf3`：新增 `lib/skills/versionOrigin.ts`，把 `created_by` 映射为本地化的来源名称（Agent 修改 / 手动编辑 / 技能成长 / 回滚 / 导入 / AI 优化），未知来源直接省略，不展示原始标识；`createdByLlm` 由「LLM 优化」改为「AI 优化」，六种语言同步；
5. 文档 `ef6148e871`、品牌仓库 `a40d61da`、根仓库 `c67375633`：公开的技能演进文档（英 / 中 / 韩）把「A/B 测试」换成代码里真实存在的「改进闸门」（派生路径把原技能作为基线候选）；竞品对比页把 50 个上限写成数量并说明满载提示，同时去掉一句与技能演进无关、无出处的端到端测试说法；官网评价文案、内部优势材料与路线图同步去掉已不存在的说法；`skill_optimization` 包的文档串与 fractal 头部基线里的影子链残留一并清掉。

### 验证

1. harness：`tests/agent/skills/evolution` 393 通过（含按数量判定、修复类放行、`count_active_skills` 与过滤条件一致的用例）；
2. 服务端：容量守卫、实时核对、事件发布、进化运行时、进化引擎任务 5 个测试文件共 28 通过；
3. 前端：`hooks/globalEvents`、`lib/skills`、`components/features/skills` 33 个测试文件 198 例通过（新增 `skillCapacityToast.test.ts` 5 例、`versionOrigin.test.ts` 11 例）；
4. `verify-i18n` 六种语言的键对齐、占位符、术语与翻译壳检查通过；`verify-i18n-references` 目前仍报 53 个他人组件的缺失键，没有一条属于本次涉及的文件或键；
5. Prompt Cache：`scripts/measure_turn1_token_inventory.py --json` 的输出与改动前基线逐字段相等（15 个工具、工具小计 6,438 token），系统提示、工具定义与已绑定技能均未改动；`tests/architecture/test_prompt_token_budget_gate.py` 3 例通过；
6. 容量检查耗时（单次实测，机器负载约 40，进化库 60 条记录）：未满时 0.491 毫秒，满载并核对实际技能时 18.701 毫秒/次；
7. Chrome E2E 未通过：按正式流程（`./myrm ready --attach --chrome` → `e2e-context launch-check` → `./myrm test -m chrome_e2e`）对 `test_growth_center_chrome_e2e.py::test_growth_center_stats_and_lazy_detail_in_real_ui`（它打开的正是本次改过的 `PendingEvolutionsDashboard` 所在页面）试跑 5 次，没有一次通过：第 1 次页面里成长面板始终没有出现（9 分 36 秒）；第 2、5 次页面脚本最慢的块加载 89 秒左右，React 桥接在期限内没有就绪（各约 4 分钟，第 5 次结束时机器负载均值 107）；第 3 次私有 epoch 后端 43 秒内没有对齐，第 4 次共享热池恢复期内附加失败，这两次测试体都没有启动。试跑间隙对同一路由的 GET 返回 200（0.9 秒），57 个脚本块串行取完 128 秒（负载均值 77），测试匹配的文案（`Skill Growth` / `Total Cases` / `Pending Review`）与 `locales/en.json` 一致；失败发生在脚本加载阶段，不是断言内容，这既不能证明本次改动有问题，也不能当作通过；

### 踩坑经验

1. 「删除」必须写回计算容量的那份数据：容量按 A 处计数、用户在 B 处删除，规则就永远不会松开；改成数量规则之后，达到上限时还要对照实际技能核对一次，否则同样的问题只是换了个数字；
2. 为保护提示词而设的 token 上限，量的却是按需加载的正文，每回合付出全量分词的代价、拿不到任何保护；与其调参数，不如删掉这条规则；
3. 往没人订阅的通道推送等于没推送，加推送前先搜订阅端；这次的 `/ws/evolution` 从后端到前端没有一个连接方；
4. 删除一条链要把公开文档、官网、路线图与基线文件当成同一次改动；影子 A/B 删除后，三处公开文案仍在宣称它；
5. 共享工作区里同一批文件带着他人的未提交改动：提交时用「HEAD 文本 + 精确锚点替换」生成，再核对文件集合与残留 hunk，而不是挑 hunk 或整文件提交；
6. 局限：Chrome E2E 没有通过（见验证 7），现有 E2E 也没有一条覆盖满载 toast 与版本历史的来源标签；满载提示只走进程内事件总线，推给当时已连接的 WebUI / 桌面端；没有客户端连接时只能靠总线向新订阅者重放最近 100 条事件补发（服务重启即丢；重放还会让重新打开的页面在空间已释放、服务端尚未清除标记时再弹一次），IM 通知（`adaptive_cards` 的事件模板）与 Web Push 都没有该事件的模板、不转发，所以只用 IM 的用户看不到；品牌仓库公开文档里「学习不会悄无声息地停下」的说法已撤回（品牌仓库 `629611ea`）；用户删除技能时 `skills_service.delete_skill` 不碰进化库，启动时的孤儿清理只处理插件技能，已删技能的记录一直留在进化库里，所以进化库记录数一旦达到 50，之后每个满足触发条件的回合都走在库核对路径，与真实在库数量无关：单次实测（机器负载均值 34 到 55，在库 20 个技能）记录数 50 / 120 / 520 / 2020 条时每次约 7 / 8 / 25 / 49 毫秒，约一半花在读取完整记录上，没有优化；根治办法是删除与归档时同步失活进化记录，涉及多条删除路径，没有做；`useGlobalEvents.ts` 已有 719 行，超过单文件 500 行上限，本次只加了接线的 4 行，该文件上有他人未提交的改动，没有拆分；没有做浏览器级别的视觉检查（满载 toast、版本历史新标签在深浅主题下的显示）；新增的 de / ja / ko / zh-TW 译文只经过机器门禁；删除 `/ws/evolution` 后待人工审核的提案没有实时通知（旧的推送本来就没人接收，需要用户打开页面才看到，没有补 SSE）；待审核页的容量条是删除而不是改成服务端下发，要不要在页面上保留容量表是产品决定；服务端提交依赖 harness 提交 `d46a104e1`，harness 发版后要执行 `./myrm harness sync-lock`；`fractal_header_baseline.txt` 里另有 5 条他人删除文件留下的过期项（`api/skill_optimization/routes/{dashboard,optimization,system}.py`、`api/skills/{audit,quality}.py`）未动，对门禁无害；`SKILL_EVOLUTION_ADVANTAGE.md` 里带日期的测试结果表与 `de/auto-translated-overrides.json` 里已删词条的过期项没有改；`verify-i18n-references` 的 53 个缺失键来自他人组件，仍在，非本次引入。

---

## BUG-AGENT-2026-10-14-014: 凭证页对能自动续期的授权常态误报「即将过期 / 已失效」；xAI 刷新被套餐拦截（403）时被当成授权已撤销，并永久停止刷新

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P3（只影响凭证页的状态展示与 xAI 套餐被拦截时的提示与重试；不丢数据，对话里的令牌仍按原路径续期） |
| 影响范围 | server：`app/services/agent/oauth_token_policy.py`（`classify_refresh_failure`、新增 `is_renewable`）、`oauth_refresher.py`（新增只读 `is_refresh_rejected`）、`app/api/integrations/oauth.py`（列表项新增 `renewable`、`needs_reauth`）；frontend：`settings/sections/integration/credentials/{credentialsConstants,credentialsOAuthUtils}.ts`、`CredentialsOAuthPanel.tsx` |
| 出现次数 | 1（读代码、真实函数执行与单元测试确认；没有真实 SuperGrok 账号，xAI 刷新失败的响应体形态没有端到端验证） |
| 关联 | `BUG-AGENT-2026-10-14-008`（订阅登录加固；本条修正其中刷新失败分类对 403 的处理）· harness `BUG-HARNESS-2026-10-14-018`（同一批次：xAI 额度耗尽的 403 诊断） |

### 现象

1. 凭证页按访问令牌的 `expires_at` 判卡片状态（`credentialsOAuthUtils.ts`）：7 天内显示「即将过期」，已过期显示「已失效」并给「一键修复」。带 refresh_token 的授权（xAI、Google Workspace 等）访问令牌只有数小时到一小时，`expires_at` 只在有 Agent 回合触发刷新时才更新，于是：登录后立刻显示「即将过期（1 天）」，空闲超过令牌寿命显示「已失效」。真实函数执行：6 小时寿命的新令牌得 `{expiring, daysLeft: 1}`，空闲 7 小时得 `{expired}`。
2. `classify_refresh_failure` 把任何带非空字符串 `error` 的 4xx（含 403）判为终态（`oauth_token_policy.py` 的旧判定与 `test_oauth_token_policy.py` 的 `(403, {"error": "access_denied"})` 用例）。终态会按指纹记住刷新令牌、此后不再尝试刷新，并发「请重新登录」事件。Hermes 对同一 xAI 令牌端点的处理（`hermes_cli/auth_xai.py:323-342`，其 issue 编号 #26847）：403 是套餐 / 权益拦截，重新登录无效，只有 400 与 401 才要求重新登录。

### 根因

1. 卡片状态把「访问令牌的寿命」当成「连接的寿命」；列表接口只返回访问令牌的 `expires_at`，没有告诉界面这个授权能否自行续期、刷新令牌是否已被供应商拒绝。
2. 刷新失败分类只看「4xx + OAuth 错误体」，没有区分 RFC 6749 第 5.2 节定义的拒绝授权（400，客户端认证失败时 401）与其前面的访问闸门（403 等）。

### 修复

1. server：`oauth_token_policy.py` 的 `classify_refresh_failure` 只对 400 / 401 且带 OAuth 错误体的响应判终态，其余状态（含 403）一律可重试（30 秒冷却，不记指纹、不发重新授权事件）；新增纯函数 `is_renewable`（凭证同时带 `refresh_token` 与 `token_url`）。
2. server：`oauth_refresher.py` 新增只读 `is_refresh_rejected(issuer, credential)`，只比较进程内失败记忆里的指纹与当前刷新令牌，不做 I/O、不触发刷新。
3. server：`GET /integrations/oauth` 的每项多返回 `renewable` 与 `needs_reauth`，没有网络请求、没有副作用。
4. frontend：`resolveOauthCardState` 先判 `needs_reauth`（已失效），再判 `renewable`（已连接，不看访问令牌到期），其余（手工粘贴、无刷新令牌）保持原有的 7 天预警；卡片对可续期凭证不再显示「到期时间」行，没有别的明细时整个明细框不渲染。没有新增文案。

行为说明：

1. 进程重启后失败记忆为空：此前被拒绝的刷新令牌会显示为已连接，直到下一次刷新尝试再次遇到拒绝；拒绝仍会按原有路径发（去重的）重新授权事件。
2. xAI 刷新被 403 拦截后每 30 秒最多再试一次，不再弹「请重新登录」，也不再永久停止刷新。

### 验证

1. server：新增 / 改写 `test_oauth_token_policy.py`（403 与 404 / 407 等访问闸门为可重试，`is_renewable` 5 种缺失组合）、`test_oauth_refresher_failure_memory.py`（`is_refresh_rejected` 只认被拒绝的那枚刷新令牌，xAI 风格的 403 响应体不进失败记忆、不发事件）、`test_oauth_api.py`（列表三种凭证的两个字段，加 FE 类型声明了服务端列表的每个字段的契约检查）；OAuth 相关 10 个 server 测试文件加 `tests/api/integrations` 共 419 例通过、2 例跳过。
2. frontend：新增 `credentialsOAuthUtils.test.ts`（真实函数 + 假时钟：新登录、空闲超过寿命、被拒绝、手工令牌的预警与过期）与 `CredentialsOAuthPanel.test.tsx`（渲染真实面板：可续期卡片为已连接且无到期行，手工令牌保留到期行与预警，被拒绝显示已失效与修复按钮）；`settings/sections/integration` 下 30 个文件 189 例通过。
3. 变异检查（临时改写源码、跑测试、恢复原文并比对）：server 5 个（403 退回终态、`is_renewable` 的与改或、失败记忆忽略发行方、忽略令牌身份、列表丢掉 `needs_reauth`）、frontend 4 个（忽略 `needs_reauth`、忽略 `renewable`、到期行总是显示、FE 类型缺 `renewable`），全部杀死。
4. 静态：`ruff check` / `ruff format --check`、mypy（3 个 server 源文件）、oxlint、prettier、ReadLints 通过；`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx(68,3)`。
5. 局限：没有真实 SuperGrok 账号与浏览器，xAI 令牌端点对失效刷新令牌的响应状态与响应体未验证（403 的语义来自 Hermes 源码与 issue，不是自行抓取；若 xAI 对已失效的刷新令牌也返回 403，则不再提示重新登录，用户在对话失败后经重新连接恢复）；`needs_reauth` 只来自进程内存，进程重启或空闲超过供应商刷新令牌寿命后的失效授权，在下一次刷新尝试之前显示为已连接；没有做卡片在深浅主题与手机宽度下的视觉检查；架构门禁里 `test_api_services_vocabulary.py`、`test_api_route_consumers.py`、`test_frontend_api_client_paths.py` 的失败来自他人新增的目录与对 harness 的导入（`ConversationTurn`），与本次路径无关。

### 踩坑经验

1. 「访问令牌到期」与「授权失效」是两个状态：展示层不能拿前者推断后者，服务端要把「能否自行续期」与「是否被供应商拒绝」作为事实交给界面。
2. 同一状态码在不同服务上含义不同：RFC 只在令牌端点定义了 400 / 401，403 属于供应商自己的访问闸门，不能当成「刷新令牌被拒」。

---

## BUG-AGENT-2026-10-14-015: 「安全清空」把没做的事报成成功（会话检查点没清、记忆事件数恒为 1）；过期的浏览器登录会话只有一个接口会清、且只清全局保险库，定时维护从不清

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P3（`POST /api/v1/health/database/safe-purge` 目前没有界面调用方；过期会话文件只占磁盘、不再被读取；不影响对话与登录行为） |
| 影响范围 | server：`app/services/system/vault_purge_service.py`、`app/api/health/router.py`（响应新增 `purged_memory_events` 真实计数与 `checkpoint_cleared_chats`）、`app/core/security/browser_vault.py`（新增 `cleanup_all_vaults`）、`app/api/browser_sessions/router.py`、`app/lifecycle/browser.py`（删除无调用方的函数）、`app/lifecycle/schedulers.py`（DB 维护任务新增会话清理） |
| 出现次数 | 1（读代码、真实 SQLite / 真实 LangGraph 检查点库 / 真实文件保险库复现与单元测试确认） |
| 关联 | harness `BUG-HARNESS-2026-10-14-016`（检查点包装器补转发 `adelete_thread`，本条是它在「安全清空」上的调用方）· 该条「踩坑」里记下的 `cleanup_expired_browser_sessions` 无调用方，本条处理 |

### 现象

1. 「安全清空」的结果字段 `cleared_checkpoints` 只要检查点对象有 `adelete_thread` 属性就写 1，代码里没有任何一处调用它；`purged_memory_events` 在 `purge_memories=True` 时恒写 1，与实际删了多少行无关。清空后会话的检查点线程原样留在库里。
2. `POST /browser/sessions/cleanup`（设置页「已保存的登录会话」卡片的清理按钮调用它）只清全局保险库，各 Agent 的保险库不清；`lifecycle/browser.py` 里同时清两处的函数没有任何调用方；每 6 小时的 DB 维护任务不清浏览器会话。过期会话只在被读取时才会被删（`SessionVault.load` 遇到过期即删除），没有再被访问的域名，其过期文件在 Agent 保险库里一直留在磁盘上。

### 根因

1. 清空服务只做了「探测能力」（`hasattr`）而没有「执行并计数」；旧测试只播种 1 行待处理记忆并断言 `purged_memory_events == 1`，与写死的 1 无法区分，检查点计数则没有任何断言。
2. 「清全部保险库」的逻辑写成了一个无人调用的函数，接口另写了一份只清全局的，定时任务没接入；三处各自为政，没有单一入口。

### 修复

1. `SafeVaultPurgeService` 在聊天行被删之前，对每个聊天调用 `sync_checkpoint_messages(checkpointer, chat_id, [])`（两种线程别名都删，失败抛 `ContinuitySyncError`）：单个聊天失败只记 WARNING 并跳过，不中断清空；结果字段改名为 `checkpoint_cleared_chats`，数的是「检查点线程已清掉的聊天数」（该聊天本来没有线程也计入，不是线程条数）；检查点对象未注册时记 WARNING、计数为 0、其余照常清空。先删检查点再删聊天行，是为了被中断的清空不会留下再也列不出来的检查点。记忆管线的三张表按 `rowcount` 累加成真实计数；从未被赋值的 `freed_disk_bytes` 字段删除；API 响应补上 `purged_memory_events`、`checkpoint_cleared_chats`。
2. `browser_vault.py` 新增 `cleanup_all_vaults()`（全局 + 全部 Agent 保险库），接口与 DB 维护任务共用；任务内的清理失败只记日志、不影响同一周期的其余维护项；删除无调用方的 `cleanup_expired_browser_sessions`。

### 验证

1. A：`tests/services/system/test_safe_vault_purge_service.py`（真实 SQLite 加真实 LangGraph 检查点库：每个聊天的两种线程别名都被清掉、清空前先清检查点、单个聊天失败不中断、未注册检查点仍完成清空、记忆管线真实计数）；4 个变异（跳过检查点清除、清除顺序放到删聊天之后、失败即中断、计数写死）全部杀死。
2. B：`tests/config/test_browser_vault.py`（真实文件保险库：过期的删、未过期的留，全局与各 Agent 保险库都覆盖）、`tests/api/browser_sessions/test_browser_sessions_cleanup_api.py`、`tests/lifecycle/test_db_maintenance_browser_sessions.py`（真实 `_db_maintenance_job` 调用清理，清理失败时其余维护项照常执行）；3 个变异（只清全局、定时任务不调用、接口退回只清全局）全部杀死。A 与 B 加上 `tests/channels/test_channel_data_plane.py` 共 45 例通过。
3. 静态：本次改动的 server 与 harness 文件 `ruff check` / `ruff format --check` 通过；`hop_evaluator.py` mypy 通过。`browser_vault.py` 的 mypy 报错（行 51、66、99、144 的 `"object" not callable`）来自 harness `toolkits.browser` 的惰性导出被推成 `object`，不在本次改动的行内，未处理。
4. 局限：
   - 没有清真实的向量库（Qdrant）条目，这一步本来就不在清空服务里，也没加；没有用真实用户数据库验证；清空接口仍没有界面入口，本条只修了它报告的数字与实际行为。
   - 检查点只按 `chats` 表里的聊天清除；不对应聊天行的线程（看板、定时任务一类）不动，其内容是否含已被清空的会话文字未验证。
   - 设置页卡片只列全局保险库，清理按钮的提示个数现在含各 Agent 保险库里被删的过期会话，个数可能大于列表里看到的过期条数。
   - 每 6 小时的自动清理沿用 `SessionVault.cleanup_expired` 的行为：解密失败的文件也会被删且不留备份（`session_vault/__init__.py:475-477`；`load` 遇到同样情况会先备份再删，见 `:365-368`）；读取到删除之间没有锁，同一域名恰在此刻重新登录写入的新会话理论上可能被误删（读 `:464`、删 `:473`）。会话丢失的后果是需要重新登录，窗口为毫秒级，没有实测。

### 踩坑经验

1. 结果对象里的计数必须来自被执行的操作（`rowcount`、实际成功次数），不能来自「对象有没有这个方法」或常量；对应的测试要断言数值，而不是断言字段存在。
2. 同一件事在多处各写一份，漏的往往是没人测的那份：这里是接口、无人调用的函数、定时任务三处，现在收敛到 `cleanup_all_vaults` 一个入口。

---
## BUG-AGENT-2026-10-14-016: 渠道入站风险闸门在事件循环上无时限地跑任意正则（邮箱规则 4 万字符卡 11 秒、回溯型自定义规则可卡死进程），内置的邮箱 / 手机 / 身份证 / 银行卡规则与隐私分类器是两套口径；无噪声记忆套件的“清除记忆”只清一个进程内字典

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（闸门对每条渠道入站消息执行，文本由聊天对端控制；卡住事件循环会让整个进程无响应。口径不一致只造成误拦与漏拦；无噪声记忆卡片是展示性界面，不影响真实记忆） |
| 影响范围 | server：`app/services/risk/{constants,detection,rule_service,match_checks}.py`、`pyproject.toml`（新增 `regex`）；删除 `app/api/memory/noise_free_memory_router.py`、`app/services/memory/noise_free_memory_service.py`、`app/schemas/noise_free_memory.py` 与路由注册；frontend：删除指挥中心「无噪声记忆」卡片、子组件、服务客户端；harness 侧见 `BUG-HARNESS-2026-10-14-019` |
| 出现次数 | 1（读代码、真实函数执行与单元测试确认；没有在真实渠道上端到端验证） |
| 关联 | harness `BUG-HARNESS-2026-10-14-017`（同一个邮箱正则在隐私管线里的二次方耗时，已改为有界的 SSOT 写法，本条让风险闸门读同一份）· harness `BUG-HARNESS-2026-10-14-004`（自定义隐私模式的编译炸弹防护，本条通过公开的 `pattern_problem` 复用同一套判定） |

### 现象

1. 内置邮箱规则 `(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b` 对 4 万字符的 `a.a.a.` 连续串实测 11.2 秒；用户自定义规则用标准库 `re` 编译、没有任何匹配时限，写成回溯型（嵌套量词）即可让闸门长时间占住事件循环。
2. 内置规则各写了一份自己的正则：手机号规则会在更长的数字（订单号、运单号）里截出 11 位判为手机号；身份证规则只看 18 位形状，不校验校验位；银行卡规则在“银行卡 / bank card”后面的日期里也能凑出卡号。隐私分类器用的检测器早已修过这些，闸门没有跟上。
3. 内置规则只在首次启动时写入数据库，此后即使代码里的模式改了，库里的旧模式一直生效，而内置规则的模式用户无法编辑。
4. 「测试规则」只告诉用户命中与否，不给出命中的文本。
5. 指挥中心「无噪声记忆」卡片的“清除记忆”和“提交事实”只改 harness 提取器里的进程内字典，界面显示已清除、代次加一，用户真正的记忆没有任何变化（详见 `BUG-HARNESS-2026-10-14-019`）。

### 根因

1. 闸门在事件循环里同步匹配，规则来源（内置、用户自定义）都没有时间预算；标准库 `re` 不提供单次匹配的超时。
2. 内置规则的模式和确认逻辑与隐私层是两处各自演进的拷贝，没有读检测器的单一真源。
3. 种子逻辑是“有则跳过”，只管插入，不管已有行的模式是否过期。
4. 无噪声记忆套件的事实没有接到任何真实记忆存储，整条链路（提取器、服务、路由、卡片）互相自洽却不连到数据。

### 修复

1. `detection.py` 改用 `regex` 包：每条规则的每次匹配都带 0.25 秒的时间预算，超时按命中处理（宁可多拦也不放过，并记警告与“匹配超时”摘要）；`compile_pattern` 统一做长度上限（4096）、计数重复过大的拒绝（`regex` 会展开计数重复，`(a{1000}){1000}` 这类写法标准库 `re` 编译只要 0.1 毫秒，换成 `regex` 就必须先拦；判定复用 harness 的 `pattern_problem`）与编译，保存规则、加载规则、规则预览共用这一个入口，保存时拒绝，加载时跳过不可用的规则并记错误日志。
2. 内置的邮箱、手机、身份证、银行卡规则改用隐私检测器自己的模式来源（`EMAIL_RE`、`CHINA_PHONE_RE`、`CHINA_ID_RE`、`CARD_CONTEXT_RE`），并施加同样的确认：身份证校验位、手机与邮箱排除示例占位值（`match_checks.py`）；银行卡规则按卡号上下文取值，不再被日期触发，也不再依赖 `account number` 关键词。
3. `seed_builtin_rules` 对已存在的内置行只刷新模式，名称、严重级、动作、启用状态保持用户的设置。
4. 「测试规则」返回命中的文本片段（最多 20 条），超时给出明确的英文提示要求简化模式。
5. 删除无噪声记忆套件在 server 与 frontend 的全部代码，并移除指挥中心的挂载、`services/memory.ts` 的导出与硬编码文案基线里的两条。

### 验证

1. 新增 `tests/services/risk/test_risk_rules_engine.py`：个人数据命中 / 不命中成对用例（含订单号不是手机号、校验位错的身份证不是身份证、日期不是银行卡）、40K 点号连续串在 2 秒内完成、四条内置规则的模式可用、回溯型自定义规则被时限拦住并带“匹配超时”摘要、过大计数重复在保存时被拒绝且加载时被跳过、预览行为、种子刷新保留用户设置；`test_inbound_risk_gate_integration.py` 的夹具改用 `compile_pattern`。
2. 实测：最慢的内置规则在 10 万字符文本上不超过 10 毫秒（机器负载很高时），0.25 秒预算有 25 倍余量；40K `a.a.a.` 串的邮箱匹配从 11.2 秒降到毫秒级。
3. `tests/api/memory`、`tests/services/risk` 全绿；`app.api.memory.router` 导入后路由表里没有 noise-free 路径；前端 `features/memory` 90 个文件 542 例通过，`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx(68,3)`；本次改动的 server 文件 `ruff check` 通过，风险引擎的 mypy 无新增报错。
4. 局限：没有在真实 IM 渠道上端到端验证；银行卡规则不再把 `account number` 当触发词，只有银行卡 / 信用卡 / 卡号 / bank card / card number 等指明是支付卡的关键词后面的卡号才命中（与隐私分类器一致，没有卡号形状的账号不再被拦）；超时按命中处理意味着极端长文本上的病态自定义规则会拦截该消息（预期行为，用户在规则页能看到“匹配超时”的摘要）；server 依赖钉住已发布的 harness，本次用到的 `pattern_problem` 与 `CARD_CONTEXT_RE` 在发布新版 harness 并执行 `./myrm harness sync-lock` 之前，OSS 的锁定安装无法导入——这是维护者的发版步骤，本次没有执行；内置的护照规则对“passport renewal process”这类普通英文句子仍会误报，本次未动。

### 踩坑经验

1. 在事件循环里跑用户可控的正则，必须有单次匹配的时间预算，而标准库 `re` 做不到：用 `regex` 的 `timeout=`，并且决定好超时时是放行还是拦截（闸门取拦截）。
2. 同一类检测在两处各写一份，修好的一边会随时间偏离另一边：内置规则直接读检测器的模式来源与确认函数，不要抄正则。
3. “只在首次启动写入”的内置数据，代码里改了就要有同步路径，并且只能同步用户无法编辑的那部分。
4. 没有接到真实数据的演示型界面比没有界面更糟：它会报告“已清除”。

---
## BUG-AGENT-2026-10-14-017: 公开路径白名单按前缀放行，把前缀下的运维动作一并放行：`/api/v1/health/**` 下的数据库重置、安全清空、修复执行，`/api/v1/a2a/**` 下的对端增删与任务审批，以及 WebUI 密码保护开关，都不需要认证

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P1（本机仅回环访问时只有同机进程与浏览器页面能触达；一旦服务对局域网 / Tailscale 暴露，同网络上任何人无需凭据即可调用，其中数据库重置会直接删除 SQLite 文件） |
| 影响范围 | server：`app/core/security/auth/public_paths.py`（`is_public_path` 增加方法参数）、`app/middleware/{auth,host_allowlist,ws_auth}.py`、`app/core/security/auth/identity.py`、`app/api/webui/auth_routes.py`（保护开关 handler 自行认证）；frontend：`BrowserDoctorCard`、`CloudBrowserCard`、`BrowserProxyCard`、`MemoryMonitorCard` 的变更类请求改走 `apiRequest` |
| 出现次数 | 1（枚举全量路由表、读 handler、真实中间件链的单元与门禁测试确认；没有在真实的局域网暴露部署上端到端验证） |
| 关联 | `BUG-AGENT-2026-10-14-015`（「安全清空」所在的路由前缀；本条是发现它属于公开前缀时一并发现的） |

### 现象

1. `PUBLIC_PATH_PREFIXES` 含整段 `/api/v1/health`，认证、Host/Origin 白名单（DNS 重绑定防护）、WebSocket 握手三处都按它放行。该前缀下实际有 8 个非 GET 路由：`POST /health/database/reset`（删除数据库文件）、`POST /health/database/safe-purge`（清空全部会话）、`POST /health/repair-actions/{action_id}/execute`、`DELETE /health/browser/orphans`、`POST /health/browser/test-cloud-connection`、`POST /health/browser/test-proxy-connection`、`POST /health/memory/profile/start`、`POST /health/memory/profile/stop`。
2. 同一机制放行了整段 `/api/v1/a2a`：RPC 与 AgentCard 发现本来就该公开（对端用 Bearer 令牌，未受信对端的任务只进「待审批」队列），但同前缀下的运维路由也跟着公开：`POST/PATCH/DELETE /a2a/peers`、`POST /a2a/peers/probe`、`POST /a2a/tasks/{id}/approve|reject`、`GET /a2a/tasks/pending-approval`。未受信对端提交任务后，可以自己调 approve 绕过「运维人员审批」。
3. `PUT /webui/auth/protection` 在公开前缀 `/webui/auth/` 下，handler 里没有任何身份检查，一个无会话的远程客户端能把「需要登录密码」关掉（同组的 `change-password`、`disable-protection`、`generate-setup-token` 都在 handler 内校验了密码或会话，只有它漏了）。
4. 本机模式下 `HostAllowlistMiddleware` 对公开路径整体跳过，所以外站网页发往 `http://127.0.0.1:<port>/api/v1/health/database/reset` 的跨源 POST 也不会被 Origin 检查拦下。

### 根因

公开规则只看路径前缀，不看方法：为了让探活 GET 免认证而公开了整段前缀，前缀下后来加的变更类运维路由默认继承了「公开」。没有任何门禁检查「哪些变更类路由是公开的」，所以新增或挪动路由时没人会发现。

### 修复

1. `is_public_path(path, method)`：`/api/v1/health` 改为只读前缀（只对 GET/HEAD 公开）；`/api/v1/a2a` 整段前缀换成精确的公开面：`/api/v1/a2a/rpc`、`/api/v1/a2a/agents/` 前缀（每个 Agent 的 RPC 与发现）、`/api/v1/a2a/.well-known/agent-card.json`；对端与任务审批管理路由不再公开。四处调用点（HTTP 认证、身份解析、Host/Origin 白名单、WebSocket 握手）都传方法；方法参数无默认值，漏传会在类型检查时暴露。
2. `PUT /webui/auth/protection` 在 handler 内用 `resolve_status` 判断，未认证返回 401；回环且本机无需密码时仍视为已认证，带会话的请求照常通过。
3. 新增门禁 `tests/architecture/test_public_mutating_routes.py`：全量路由表里任何对外开放的变更类路由，必须登记「handler 自己怎么认证」（13 条，含 A2A 两个 RPC、分享链接三个路由、`/webui/auth/*` 八个），未登记或登记后不再公开都会失败。
4. 前端 5 处对这些路由的 raw `fetch`（没有带认证头，也不走 `BACKEND_BASE_URL`）改为 `apiRequest`；两处 GET（健康检查、记忆历史）仍是公开的，不动。

### 验证

1. `tests/core/security/auth/test_public_paths.py`（80 例：8 条健康运维路由 × 4 个变更方法、6 条 A2A 运维路由 × 全部方法、公开面保持公开）、`tests/middleware/test_auth_middleware.py`（远程模式下无凭据的 POST `/health/database/reset` 与 `/a2a/tasks/{id}/approve` 返回 401，带 API Key 通过，`/health` GET 与 `/a2a/rpc` 保持公开）、`tests/middleware/test_host_allowlist_middleware.py`（外站 Origin 的变更类健康路由返回 403、GET 探活仍通）、`tests/services/webui/test_protection_session_policy.py`（非回环无会话 401 且开关未变；带会话 200）、门禁 2 例。变异检查：把规则改回旧的整段前缀，66 例失败（单元、门禁、中间件、Host 白名单四层都杀死）；保护开关的 401 用例在加认证判断之前实测返回 200（红灯）。
2. 前端：`BrowserDoctorCard`（19 例，清理改走 mock 的 `apiRequest`）、新增 `BrowserConnectionCards`（6 例）与 `MemoryMonitorCard`（4 例）共 29 例通过；变异（云端浏览器卡改回 raw `fetch`）3 例失败；本次改动文件的 `tsc --noEmit` 无错误（全仓库还有他人未提交改动导致的 Kanban 类型错误，不在本次范围）。
3. 静态：本次改动的 server 文件 `ruff check` / `ruff format --check` / mypy 通过（顺带修了 `identity.py`、`ws_auth.py`、`auth_routes.py`、测试夹具里原有的 mypy 错误与 `host_allowlist.py` 的格式问题）。
4. 局限：
   - 未验证真实部署：云托管入口前置的网络层是否已经挡住这些路径、远程模式下 Bearer 令牌的实际流转，都没有在真实环境里测。
   - `change-password` 与 `disable-protection` 校验密码但没有登录那样的失败次数限制，未认证远程客户端可以不限速地试密码（`auth_service.py:231-256` 对比 `:194-203` 的 `_is_rate_limited`），本条没有改。
   - A2A 的 `tasks/get` 与 `tasks/cancel` 对任何调用者开放（不区分是否受信对端），靠任务 ID 不可猜测；本条没有改。
   - 本次新增的 `MemoryMonitorCard` 测试里卡片自身仍有硬编码英文文案（`Start Heap Profiling` 等），未在本条处理。

### 踩坑经验

1. 「前缀公开」是一个会随时间放大的授权：每个挂在公开前缀下的新路由都默认免认证。公开规则要么精确到路径、要么带方法，并且要有门禁列出所有「公开的变更类路由」，让新增者必须说明它怎么自己认证。
2. 同一组路由里「大部分有校验、个别漏掉」最容易漏检：`/webui/auth/*` 八个变更路由里七个自己校验，只有保护开关没有。
3. 前端对受保护接口用 raw `fetch` 在本机模式下看不出问题（回环被信任），一旦接口收紧，远程模式才会 401；对内接口统一走 `apiRequest`。

---

## BUG-AGENT-2026-10-14-018: 后台自动学习只拦 CRITICAL，带外传 / 提权 / 持久化行为的技能草稿直接物化；运行时进化的自动合并不看安全扫描；修订提案遇到任意一条发现就被判扫描失败；待审核卡片把内部风险代码原样印给用户；会话结束触发的 CAPTURED 提取与容量暂停整条链无人受益

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P1（默认开启的后台学习会在无人审阅时落地含 HIGH 级风险行为的技能；其余为 P2/P3） |
| 影响范围 | 服务端 `app/services/skills/scan_risk_policy.py`（新增）、`skills/growth/lifecycle.py`、`skills/auto_extractor.py`、`skills/draft_notification.py`、`skills/evolution_review/actions.py`、`app/services/agent/confidence_approval_flow.py`、`stream_session/stream_finalize.py`、`skills/evolution_events.py`、`event/app_event_bus.py`（删除 `app/services/agent/evolution/engine.py`）；前端 `lib/skills/scanRiskText.ts`、`components/features/skills/`（成长卡片拆出 `growth-card/`）、`hooks/globalEvents/`、`PendingEvolutionsDashboard`、六种语言文案；品牌仓库竞品对比页与根仓库优势材料 |
| 出现次数 | 1 |
| 关联 | `BUG-AGENT-2026-10-14-013`（该条引入的容量暂停与满载提示，本条整体撤销，原因见根因 5）；本地提交，未 push |

### 现象

1. 默认开启的后台复盘（`process_skill_review_result`）对技能草稿只做 CRITICAL 预检；一份把数据上传到外部地址、改权限或写入开机项的草稿，只要没有 CRITICAL 发现就直接物化为可用技能；预检只扫描草稿的步骤文本（`skill_steps`），描述与触发条件不在扫描范围内，也没有把它当成一份完整的 SKILL.md 扫描；
2. 运行时失败触发的进化提案（`ConfidenceApprovalFlow`）自动合并只看改动幅度与历史成功率，一次改动凭空多出的 HIGH 级风险不影响是否自动合并；
3. 修订待审提案时，新内容只要有任何扫描发现（含 LOW / MEDIUM，甚至原本就存在的）就被标成 `FAILED_SCAN`，用户无法继续审阅；前端又用 `test_passed === false` 判断结果，对「仅有 HIGH、仍待审」的修订会误报失败；
4. 待审核卡片、本地技能预览与技能详情把风险信号码（`diff_range:73%`、`low_effective_rate:20%(5runs)`）、威胁类别码（`data_exfiltration`）和英文处置建议原样展示给用户，非英文界面也是英文；
5. 会话结束触发的 CAPTURED 提取（`trigger_skill_evolution`）与 `13` 号条目的「技能库满载暂停学习」两条链：默认的后台复盘已覆盖同一目的，CAPTURED 提取只在显式开启进化时运行；容量暂停只挡住这条可选链，对默认路径没有任何约束，而技能库的上限由 Curator 负责（活跃技能超过 `max_skills=50` 时把最久未使用的标记为过期），满载提示因此既不会在默认路径触发，也与 Curator 的规则重复。

### 根因

1. 后台学习的闸门只回答「有没有 CRITICAL」，没有回答「这次让技能多出了什么需要人看一眼的风险」；
2. 后台复盘的结果里没有 `content`，只有 `skill_name / skill_description / trigger_condition / skill_steps`，闸门没有先渲染出 SKILL.md 就扫描；
3. 修订闸门把「扫描不干净」当成「扫描拒绝」，与扫描器自己的 `REJECT` 建议（CRITICAL）是两个口径；
4. 服务端只下发稳定的码，展示层没有统一的翻译出口，每个渲染点各自处理；
5. 容量暂停链建在一条可选路径上，没有核实默认路径是否经过它；上限本来就有 Curator 这个单一责任方。

### 修复

1. 新增 `scan_risk_policy.assess_scan_risk(skill_name, proposed, *, original=None)`：对「新内容 − 原内容」按 `(威胁类别, 描述, 严重度)` 做多重集差分，只统计 HIGH 及以上；同类发现数量增加仍算新增（复制一行有风险的内容不会被当成「原本就有」）；`filesystem_access / memory_config_snooping / network_access / path_traversal / prompt_injection / screen_input` 六类取决于技能用途（GUI 技能必然截图点击、联网技能必然访问网络），HIGH 不计，CRITICAL 仍计；新技能的原内容为空；扫描器抛异常按「扫描不可用」处理，不放行；扫描放进 `asyncio.to_thread`，大技能不会占住事件循环；
2. 后台复盘：在 CRITICAL 硬拦截之后、物化之前渲染 SKILL.md（`render_skill_draft_markdown`）并评估；有新增 HIGH 风险或扫描不可用时落为 `PENDING_REVIEW` 草稿，`reason_code = "risk:" + 信号列表`，并把扫描摘要写入 `security_scan_summary`，卡片可展示；
3. 运行时进化：`ConfidenceApprovalFlow` 新增信号 `new_high_finding:<类别>` 与 `scan_unavailable`，任意一个出现都降为人工审批，处置建议随信号给出；
4. 修订闸门：只有扫描器判定 `REJECT` 才进入 `FAILED_SCAN`；仅有 HIGH 的修订仍待审并保留发现；前端 `PendingEvolutionsDashboard` 改按 `result.status === 'FAILED_SCAN'` 报失败；删除 `SkillGrowthReviseResult` 里没人读的 `test_passed`；
5. 删除 CAPTURED 触发（`evolution/engine.py`、`stream_finalize` 的触发调用）与容量暂停链（服务端容量检查与 `SKILL_CAPACITY_REACHED` 发布、前端 `skillCapacityToast`、六种语言的 `skillCapacityReached` 等文案）及对应测试，品牌仓库竞品对比页与根仓库优势材料里的「满载提示 / 容量暂停」说法改为 Curator 的自我收敛；顺带删除 `stream_finalize` 里已无调用方的 `record_citations` / `get_memory_manager` 分支并补全类型；harness 的 `capture_skill_from_trajectory` 与 `SkillBudgetGovernor` 作为库接口保留，产品不再调用；
6. 前端新增 `lib/skills/scanRiskText.ts` 与 `useScanRiskText`：威胁类别与严重度以封闭词表判定（词表外显示「其他风险」，不暴露代码），风险信号翻译为带数值的自然语言，处置建议按信号种类各一句且去重；成长卡片、本地技能预览、技能详情共用；`SkillGrowthCaseCard.tsx` 由 634 行拆为 340 行并移出行数基线，子区块在 `growth-card/`；六种语言新增 `settings.skills.scanRisk`。

### 验证

1. 服务端：本次涉及的 7 个测试文件共 80 例通过，其中新增 `test_scan_risk_policy.py` 11 例（真实扫描器）、`test_skill_scan_threat_i18n_sync.py` 12 例（扫描器可报告的全部威胁类别与六种语言译文键完全一致），并在后台复盘、运行时进化信号、修订闸门的测试里分别补了 4、3、1 例；关闭后台复盘闸门后新增的 3 例会失败（变异验证）；
2. 更宽的服务端回归 `tests/api/evolution`、`tests/api/skills`、`tests/services/skills`、`tests/services/agent/stream_session`、`tests/architecture`：2701 通过、17 失败；失败的是他人的改动，与本条无关：`test_curator.py` 4 例，`tests/architecture` 13 例（路由消费者、服务域词表、`__init__.py` 布局、前端 API 路径、server 对 harness 的深层导入基线）；本条新增的 `scan_risk_policy` 对 harness 的导入不在新增深层导入清单里；
3. 前端：全量 vitest 1383 个文件 9705 例通过；`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx(68,3)`；`verify-i18n` 六种语言的键对齐、占位符、翻译壳检查通过；fractal 文档检查通过；
4. 前端测试里 `constructor / __proto__ / toString / hasOwnProperty` 作为威胁类别或严重度时，next-intl 的 `t.has` 会把原型成员当成「存在」，直接把键路径印给用户；词表判定改为封闭数组后该用例通过；
5. 语料实测（`external_reference_project` 下去重后随机取 500 份社区 `SKILL.md`，固定种子，当作全新技能评估）：63 份（12.6%）会被拦下复核，其中 27 份（5.4%）没有任何 CRITICAL 发现，即旧闸门不会拦、新策略才会拦的那部分；拦截的类别以 `persistence` 27、`data_exfiltration` 16、`container_escape` 11、`privilege_escalation` 8 为主；单次扫描耗时中位 11.8 毫秒、p95 36.6 毫秒、最大 157.4 毫秒（机器负载较高时的单次测量）；
6. 局限：社区技能的命中率是后台自动学习草稿的上界，后台复盘产出的草稿由本人会话生成，没有用真实 LLM 端到端跑过；正则扫描器本身有盲区（`base64 -d | bash`、`curl -k` 等写法扫不出），本策略只让「扫描器已经能看见的新增风险」必经人审；自动合并阈值 0.8 没有外部依据；后台复盘路径里步骤文本会被预检与策略各扫一次，多出约一次扫描的耗时；扫描发现的 `description` 文本和应用失败面板里的 `remediation` 仍是服务端英文，未本地化；没有做浏览器级别的视觉检查（深浅主题、移动端）；`SkillHistoryPanel.EvolutionRecord.test_passed` 仍保留。

### 踩坑经验

1. 「只拦最严重一档」的闸门会让次一档里真正危险的行为静默通过；闸门应当回答「这次改动新增了什么需要人看」，并用差分而不是绝对值，否则原本就存在的发现会反复拦同一个技能；
2. 按次数差分而不是按集合差分：集合差分会让「再复制一行有风险的内容」逃过去；
3. 安全闸门里扫描器抛异常必须判为「不可用」并交给人，不能当成干净；
4. 展示层依赖 i18n 库的「是否存在该键」来决定走本地化还是兜底时，要先确认库对原型成员的行为；服务端下发的类别码这种封闭词表，用封闭数组判定最稳，再用测试把词表、译文键与扫描器三者锁在一起；
5. 给可选路径加的保护，要先核实默认路径是否经过它；一份约束如果已有单一责任方（这里是 Curator），不要在另一条链上再造一份；
6. 共享工作区里同一批文件带着他人未提交的改动：提交用「HEAD 文本 + 精确锚点替换」生成并核对残留 hunk，而不是整文件提交。

---

## BUG-AGENT-2026-10-14-019: 风控内置规则默认全开，日常聊天与代码被大面积拦下（39 条日常消息拦下 31 条），同一批规则又漏掉 7/28 种真实凭据；命中记录把被拦下的密钥原文存进库；「放行」动作没有任何作用；Web 端的拦截提示是写死的英文

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P1（默认规则把普通对话拦成常态，用户只会整体关掉风控，真正的凭据反而没人拦；命中记录以明文保存被拦下的密钥） |
| 影响范围 | server：`app/services/risk/{constants,patterns,builtin_rules,builtin_business_rules,match_checks,detection,rule_service}.py`、`app/api/risk/schemas.py`、`app/lifecycle/risk_rules.py`、`app/services/agent/stream_session/risk_gate.py`；frontend：`riskEvents.ts`、`i18nToastService.ts`、风控设置页三个文件、六种语言文案；harness：`toolkits/computer_use/recording/synthesizer.py`（见 `BUG-HARNESS-2026-10-14-020`） |
| 出现次数 | 1（用 39 条日常消息与代码、28 条凭据样本在真实规则引擎上对照新旧规则得出；没有真实用户数据） |
| 关联 | `BUG-AGENT-2026-10-14-016`（同一套引擎的时限与口径统一，本条在其之上改默认与精度）· `BUG-AGENT-2026-07-27-002`（测试夹具里的普通英文词触发风控，同一个根因的另一个症状） |

### 现象

1. 31 条内置规则首次启动全部启用。39 条日常消息与代码（“schedule the meeting”“team meeting agenda”“cookie recipe”“Set SECRET_KEY in your .env”“redis://localhost:6379”“password = input(...)”“token = 4096”“password=${DB_PASSWORD}”等）里拦下 31 条；关键词按子串匹配，`tin` 命中 meeting、`nda` 命中 agenda，赋值类规则把变量引用、占位符、数字都当成密钥。
2. 同一批默认规则对 28 条凭据样本只拦下 21 条，漏掉 OpenAI project key（`sk-proj-…`）、Anthropic key、GitHub fine-grained token、Slack token、Stripe live key、GitLab token 与 JSON 里的 `"password": "…"`。
3. 命中记录的 `match_summary` 存的是被拦下的原文（密钥、手机号、地址），设置页的命中列表直接显示。
4. 规则的动作有 `block` 与 `allow` 两种，设置页可选；`allow` 命中后只是不拦，既不放行别的规则、也不改变任何结果；`DetectionResult.highest_action` 与 `RiskAction.RANK` 没有调用方。
5. Web 端被拦时 SSE 里带的 `message` 是服务端写死的英文句子，非英文界面也是英文，也没说明去哪里关掉规则。
6. harness 的计算机操作录制里还有一份同样的邮箱正则（`synthesizer.py`），对点号连续串是二次方耗时。

### 根因

1. 默认启用与规则精度没有关联：规则按“能想到的敏感词”写，全部默认开，没有区分“命中即真泄露”（凭据）与“只是话题相关”（词汇）；关键词不带词边界；赋值类规则只看形状，不判断右值是真值还是引用。
2. 凭据规则的前缀表不全，且 `-` 不在允许字符里，带连字符的长密钥被截断后不够长。
3. 命中摘要沿用“方便排查”的写法，没有把“规则本身就是为了不让秘密扩散”这一点用在自己的存储上。
4. `allow` 动作在引擎里没有对应语义，是从没接上的设计残留。
5. 拦截文案放在服务端，而展示语言只有前端知道。

### 修复

1. 默认只启用安全凭证类别的 8 条规则（`DEFAULT_ENABLED_CATEGORIES`），其余 23 条为按需开启；已存在的安装保留各自的开关状态（库里区分不出“默认”与“用户选的”），但模式刷新照常生效。
2. 赋值类规则（`credential_assignment`、`cookie_session_like`、`env_file_secret`）捕获 `key` / `value`，由 `match_checks.is_confirmed_match` 调 harness 的 `secret_value_span` 判定右值是不是真值（排除遮罩、占位符、函数调用、模板、字段状态词、代码字符、纯数字；要求含数字或强符号）；`api_key_like` 补全前缀表并允许 `-`，带词首边界，避免 `task-…` 之类的 slug 误中；关键词规则统一走 `keyword_pattern`（ASCII 整词加可选复数，中日韩文字任意位置）。
3. 命中摘要只记位置 `chars:起-止`（超时记 `(matching timed out)`），不记原文；启动时清空既不是位置也不是超时标记的摘要（`clear_stored_match_text`）。规则测试仍显示用户自己粘贴的样本里的命中片段。
4. 删除 `allow`：`VALID_ACTIONS` 只剩 `block`，API 的 `action` 只接受 `block`，设置页不再提供该选项，删除 `highest_action` 与两个 `RANK`；库里动作不是 `block` 的规则在启动时改为停用的 `block` 规则（`disable_non_block_rules`）。
5. SSE 的 `risk_blocked` 只带规则列表（id、名称、严重度），前端用与设置页相同的规则名、用户所选语言拼出提示并指向“设置 → 安全策略 → 风控规则”；`translateI18nKeyIfPresent` 保证自定义规则回退到它自己的名字。
6. 600 多行的 `constants.py` 拆成 `constants`（词表与默认）、`patterns`（共享模式片段）、`builtin_rules` 与 `builtin_business_rules`（种子定义）。
7. harness 的 `synthesizer.py` 改读 `EMAIL_RE`（BUG-HARNESS-2026-10-14-020）。
8. 复审补充：赋值的右值里带省略号（`...`、`…`）按被截短的示例处理，不算密钥（`match_checks._assigns_secret`）；`translateI18nKeyIfPresent` 对含 `Object` 成员同名片段（`constructor`、`toString`）的键直接回退，因为 next-intl 的 `has` 会把这类键判为存在，自定义规则 id 为 `constructor` 时提示里会显示 `Object`，设置页同时只为内置规则查语系；设置页拆成 `RiskRuleRow`、`RiskRuleEditor`、`useRiskRulesTransfer`（原 503 行，现 344 行，行数基线条目删除）；开关、批量启停、删除、保存失败原先都提示“加载规则失败”，改用新文案 `actionError`；复制规则名称里写死的英文后缀 `(Copy)` 改为六种语言的 `duplicatedName`；列表里的图标按钮与开关补 `aria-label`。

### 验证

1. 新旧规则在同一份语料上对照（真实规则引擎，旧规则取自提交内容，每条规则逐条判定）：旧默认（31 条全开）拦下 31/39 条日常消息、拦下 21/28 条凭据；新默认（8 条）拦下 0/39、拦下 28 条凭据样本中的 28 条（这两份语料是照着已发现的问题挑出来的回归清单，不是独立抽样，不能当作对一般文本的误报率与召回率）；31 条全开时新规则拦下 4/39（邮箱与手机号、私网地址属于该开的规则本来就该命中；`roadmap` 出现在一个长 slug 里、`${DB_PASSWORD}` 被内部主机名规则命中，是这两条可选规则仍然存在的误报）。
2. 耗时（每条消息过全部启用规则，取 5 次最小值）：2 千字符聊天旧 1.4 毫秒 / 新默认 0.3 毫秒；10 万字符日志旧 53.1 毫秒 / 新默认 11.9 毫秒；4 万字符 `a.a.a.` 串旧 23.7 毫秒 / 新默认 8.0 毫秒。31 条全开时新规则更慢：10 万字符日志 83.3 毫秒对旧的 53.1 毫秒（关键词规则加了词边界，单条约慢一倍，没有病态规则；仍远低于 0.25 秒的单条预算）。
3. 测试：`tests/services/risk`、`tests/lifecycle/test_init_risk_rules.py`、渠道入站风险闸门与 bus 测试共 170 例通过；新增 `test_builtin_rule_precision.py` 锁定默认规则的误报与漏报语料、关键词词边界、命中只记位置、旧原文清除、`allow` 归一与 API 拒绝；前端 `riskEvents.test.ts`、`i18nToastService.test.ts` 与 `RiskRuleParts.test.tsx` 共 22 例通过（去掉 `translateI18nKeyIfPresent` 的保护后其中 5 例失败）；风控相关文件 `ruff`、`mypy`、`prettier` 通过。
4. 更宽的服务端回归（`tests/channels` 全部、架构域词表、入站隔离）6787 通过、14 失败，失败的是他人未提交的改动或未同步的测试，与本条无关：群路由与前缀触发 7 例（路由器新增的 `is_untrusted_event_sender` 调用，测试替身没有该方法）、`btw` 命令相关 3 例（`test_background_command` 2 例与缺失的命令译文 1 例）、`tests/architecture` 域词表 3 例、渠道日志脱敏 `test_redact_sensitive_with_special_characters` 1 例；本条改动的风控、生命周期、闸门与 bus 测试没有失败。
5. 真实文件语料（`external_reference_project` 里随机取的 300 个文档与 300 个源码文件，505 万字符，只含文件不含聊天；只是这一份抽样，换一份抽样数字会变，见 BUG-AGENT-2026-10-14-024）：旧规则全开 483/600 个文件命中，新默认 8 条 5/600、新规则全开 246/600。新默认的 5 处命中里 4 处不是密钥（`postgresql://user:pass@host`、LiteLLM 的 `api_key: os.environ/NAME` 引用、`Authorization=Bearer%20unrelated`、`sessionId: 'wf-ptc-e2e-session'`），1 处是测试夹具里形似密钥的假值 `API_KEY=sk-secret123456789`。省略号保护去掉的两个文件命中是文档里的截短示例 `Bearer oma_live_…` 与 `{"token":"sk-ant-oat01-..."}`（关掉保护时默认规则命中 7/600，已对照验证）。
6. 启动时的归一化（`disable_non_block_rules`、`clear_stored_match_text`）：20 万行命中记录且无需清理时首次约 100 毫秒、再次约 19 毫秒；清除其中 2 万行原文约 53 毫秒。
7. 最坏情形：1 MB 全是 `password = input() ` 的文本（5 万处候选，逐处确认后都不算密钥），默认 8 条规则合计 349 毫秒，`credential_assignment` 超过 0.25 秒时限，按命中处理（拦下）；同一文本旧的 31 条规则 511 毫秒，同样超时；10 万字符为 46.8 毫秒。时限只约束正则扫描，不约束命中后的确认循环，所以更长的文本耗时仍随长度线性增长。
8. 局限：除上面的真实文件语料外，没有真实用户聊天数据，新默认规则在真实聊天里的误报率未知；`os.environ/NAME`、`user:pass@host`、`sessionId: '…'` 这类引用或占位仍会命中默认规则；一个本身以 `sk-` 开头且后面连着 20 个以上字符的 slug 仍会命中 `api_key_like`；纯字母的密码不被 `credential_assignment` 拦下（精度优先）；旧版本导出的、带 `allow` 动作的规则文件导入会被拒绝（BUG-AGENT-2026-10-14-024 起不再认这个字段，导入后是启用的拦截规则）；已安装的实例仍保留全开的旧开关，需要用户自己关掉误报多的规则；`RiskMatch.action` 与库里的 `action` 列在本条保留（恒为 `block`），BUG-AGENT-2026-10-14-024 已整体删除；`secret_value_span` 不在 harness 的 `v0.1.0rc5` 标签里（该标签的 `secret_value.py` 没有这个函数，`git tag --contains b00705cc8` 为空），而服务端钉在 `==0.1.0rc5`，发布 harness 并执行 `./myrm harness sync-lock` 之前，OSS 的锁定安装无法导入；harness 的 `pyproject.toml` 版本是 `0.1.0rc6`，但标签 `v0.1.0rc6` 早已存在（2026-06-06），发版时要先核对版本号不与旧标签冲突——发版步骤由维护者执行，本次没有执行；没有在真实渠道与浏览器里端到端验证提示的外观（深浅主题、移动端）。

### 踩坑经验

1. 默认开启的规则必须能回答“命中就是真泄露”，话题相关的词汇规则一律按需开启；否则用户的唯一应对是整体关掉，保护反而归零。
2. 关键词匹配必须带词边界，英文短缩写（`tin`、`nda`、`vat`）尤其容易藏在常用词里。
3. 赋值类规则要判断右值是不是值：变量引用、占位符、遮罩、数字都不是密钥，同一份判定放在 harness 里，不要在业务层再抄一份。
4. 保护秘密的组件自己的审计记录也不能存秘密；只记位置就够排查。
5. 没有语义的选项不要留在界面上：一个什么都不改变的“放行”比没有选项更误导。
6. 用户可见的拦截文案由展示层按用户语言生成，服务端只下发稳定的标识。

---

## BUG-AGENT-2026-10-14-020: 会话的几种结束方式各拆各的：对回收站外的会话执行永久删除会清空它的全部消息、永久删除读不到沙箱目录而从不清 worktree、两个自动清除不清记忆与运行时缓存、清空回收站不清小组件存储；「安全清空」补做文件清理时每个会话都整库重扫金库

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P1（过期的回收站视图删除一个已被恢复的会话，会话仍在列表里但消息全没了，无法找回；其余为 P2：已删除会话的记忆、授权、worktree、小组件数据残留） |
| 影响范围 | server：新增 `app/services/chat/chat_disposal.py`（拆除步骤单一定义）、`chat_retention.py`（两个自动清除的到期策略）；改动 `chat_crud.py`、`app/database/repositories/chat_repo.py`、`uow.py`、`chat/_base.py`（`get_chat_by_id` 透传 `include_trashed`）、`app/services/system/vault_purge_service.py`、`app/services/infra/sandbox_cleanup.py`（批量清理）、`app/lifecycle/schedulers.py`；harness：`ArtifactVault.purge_by_task_ids`（提交 `5cef842a1`） |
| 出现次数 | 1（读代码 + 真实 SQLite 架构上的红灯测试确认；未在真实桌面部署与真实 Qdrant 上端到端验证） |
| 关联 | `BUG-AGENT-2026-10-14-015`（「安全清空」漏清检查点，本条把它并入同一套拆除步骤） |

### 现象

1. `DELETE /chats/trash/{id}` 对一个不在回收站的会话返回 404，但它的全部消息已被删除：`ChatRepository.permanently_delete_chat` 先无条件按 `chat_id` 删消息，再只在会话已进回收站时删会话行；服务层在同一事务里先删了 recall 索引与小组件存储，事务照常提交。红灯测试：播种一个活跃会话与一条消息，调用后消息数 0（期望 1）。触发条件：回收站列表已过期（会话在另一个标签页被恢复）后点永久删除。
2. 单个会话永久删除时读沙箱目录用的是 `get_chat_by_id`，它默认过滤 `deleted_at IS NULL`（`chat_repo.py:164-165`），而永久删除只作用于回收站内的会话，所以读到的永远是 None，`cleanup_sandbox_worktree` 这一分支从未执行，git worktree 一直留在磁盘上。清空回收站读的是回收站列表，不受影响。
3. 回收站 30 天自动清除与无痕会话 1 小时自动清除各自内联了一份删除：直接 `DELETE FROM chats`，只清 checkpoint 与工作空间。派生记忆、记忆抽取重试队列、运行时池与执行缓存、工作记忆、沙箱 worktree、小组件存储都不清。
4. 清空回收站不删小组件存储（`widget_kv.chat_id` 没有外键），也不清重试队列、工作记忆与执行缓存；单个永久删除则会清。
5. 清空回收站末尾的「FTS 优化」从未执行：它对 aiosqlite 驱动连接的 `execute` 没有 `await`，探针实测报 `coroutine 'Connection.execute' was never awaited` 且 0 行写入；同时 mypy 也报该处类型错误。

### 根因

同一件事（一个会话彻底结束）有 6 个入口，每个入口手写自己的子集，没有任何东西规定「一个会话结束必须拆哪些」，也没有测试把入口与步骤交叉起来看；永久删除的仓储函数把「是否在回收站」放在行删除上，却没有放在先于它的消息删除上。

### 修复

1. `chat_disposal.py` 定义拆除步骤：`clear_conversation_state`（checkpoint 线程经 `sync_checkpoint_messages` 全部别名 + 会话授权 + 拒绝熔断计数；checkpoint 清不干净只返回 False，授权照清）、`clear_runtime_caches`、`clear_extract_retry_queue`、`forget_chat_memories`、`remove_chat_files`、`dispose_permanently_deleted_chats`（先停生产者再抹状态）。每步 fail-open：行已提交，异常会中断后续步骤。焦点刷新、软删除、永久删除、清空回收站、安全清空都由它组合。
2. `chat_retention.py`：两个自动清除只决定哪些会话到期，删除委托 `ChatService.permanently_delete_chat`；无痕会话先直接置入回收站（不再重复跑软删除副作用）。原先内联在 `schedulers.py` 的两段删除代码移除。
3. 仓储：永久删除的消息删除带 `EXISTS(回收站内的该会话)` 条件，单条语句，不先 SELECT（读事务会让写事务无法升级为 `BEGIN IMMEDIATE`）；服务层在行删除成功后才删 recall 索引与小组件存储；沙箱目录读取传 `include_trashed=True`；清空回收站补删小组件存储。
4. 删除清空回收站里从未执行的 FTS 优化块，不复活：真实执行的成本实测为 18000 条消息 0.56 s（首次）到 1.7 s，且发生在写事务里、请求路径上，收益没有验证。
5. 「安全清空」：逐会话停运行时工作、清检查点与授权（行删除前），行删除后移除全部会话的 worktree 与工作空间（受 `purge_sandboxes` 控制）。`cleared_sandboxes` 仍是移除的 worktree 数。
6. 文件清理改批量：`WorkspaceCleanupService.cleanup_chat_workspaces` 与 harness `ArtifactVault.purge_by_task_ids` 让共享金库整批只扫描一次。`purge_by_task_id` 委托它，匹配规则只有一份。

### 验证

1. `tests/services/chat/test_chat_disposal.py`（17 例）：永久删除 / 清空回收站 / 回收站自动清除 / 无痕自动清除四个入口用同一张表断言：会话行、消息、小组件存储、两个 checkpoint 别名、会话授权全部消失，运行时池、执行缓存、工作记忆、记忆级联、重试队列、worktree、工作空间各被调用一次且参数正确；回收站外会话永久删除返回 False 且消息、小组件、检查点、授权原样；批量入口只调一次工作空间清理；各步骤单测含失败不阻断后续。`tests/services/infra/test_sandbox_cleanup_batch.py`（3 例，真实文件系统）、harness `tests/agent/artifacts/test_vault_purge.py` 新增 2 例。
2. 变异检查（7 个，全部被杀死后还原并比对）：拆除跳过 checkpoint（5 例失败）、清空回收站跳过拆除（1）、仓储去掉回收站条件（1，即现象 1 的红灯）、沙箱目录读取去掉 `include_trashed`（3）、无痕清除跳过置入回收站（1）、清空回收站改回逐个拆除（1）、金库改回逐个扫描（1）。
3. 实测（临时目录，真实 SQLite 检查点与 SQLite 库）：1000 个会话、金库 500 个对象时，逐个清理推算 13.2 s、批量 92.6 ms；金库 5000 个对象时推算 159.8 s、批量 642.9 ms（逐个清理单次实测 13.2 ms / 159.8 ms）。完整「安全清空」1000 个会话 1.6 s 到 4.5 s（含检查点、运行时、行删除、工作空间批量清理；两次运行的差异来自首次冷启动，未做多轮统计）。
4. 静态：改动的 server 与 harness 文件 `ruff check` / `ruff format` / mypy 通过（顺带修了 `chat_crud.py` 的类型错误、`test_external_agent_pool_on_chat_delete.py` 两处多余的 `type: ignore`、harness `vault.py` 的 `get_manifest` 返回类型）。
5. 局限：`empty_trash` 仍只取前 10000 个回收站会话做拆除，而仓储一次删光全部；清空回收站在列表与删除之间被恢复的会话仍会被拆除（均为原有行为，未改）；记忆级联、worktree 在拆除测试里是 spy，真实 Qdrant 与真实 git worktree 没有端到端验证；一次误操作对 `app/services` 整个目录跑了格式化（已把能还原的 62 个文件还原到 HEAD，4 个带他人未提交改动的已跟踪文件与 23 个他人新增文件只剩格式变化，见最终报告）。

### 踩坑经验

1. 「FK 级联绕过子表触发器导致 FTS 孤儿行」的说法在 `PRAGMA foreign_keys=ON`（`database/factory.py:82`）下不成立：真实架构上直接 `DELETE FROM chats` 后 `messages_fts` 命中数为 0，所以自动清除原先的直接 SQL 删除并没有 FTS 孤儿行，这条没有当 bug 处理；
2. 「入口 × 步骤」交叉表才能抓到「读沙箱目录读到 None」这种单入口测试写不出来的缺陷，它在第一次跑矩阵时就红了；
3. 把按会话循环的清理改批量前先量：单次 13 ms 看起来无害，乘上会话数与金库大小就是分钟级；
4. 共享工作区里不要对目录批量格式化：只格式化自己改的文件。

---

## BUG-AGENT-2026-10-14-021: 看板里失败的任务没有任何可用的重试入口（菜单与抽屉里的「移至就绪」必被服务端拒绝），拖到不可能的列要等服务端报错且把服务端原文印给用户；归档（单个与批量）没有确认；确认对话框遇到无空格长标题会撑破；三处原生对话框写死中文

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（任务耗尽重试预算后，人在界面里无路可走；其余为误导性提示与缺失的二次确认） |
| 影响范围 | harness：`toolkits/kanban/retry.py`（新增）、`dispatcher_failure.py`、`_orchestrator_tools.py`（提交 `f3057d1a9`）；server：`app/services/kanban/retry_ops.py`（新增）、`service_mixins/board_task_mixin.py`、`app/api/kanban/routes/tasks.py`（提交 `d420921820`）；frontend：`kanban-transitions.ts`（新增）、`useKanbanTaskActions.ts`（新增）、`KanbanTaskActionConfirm.tsx`、`KanbanBoardView.tsx`、`useKanbanDnD.ts`、`KanbanTaskCardActions.tsx`、`KanbanTaskDrawer*.tsx`、`KanbanBulkActionBar.tsx`、`app-shell/confirm-dialog.tsx`、`lib/utils/clipboardUtils.ts`、`memory/command-center/ConclusionAttributionStudioCard.tsx`、6 个语言包 |
| 出现次数 | 1（读代码 + 单元 / 集成测试 + 生产构建在真实 Chrome 里对着模拟接口复核；未对真实服务端与真实模型端到端） |
| 关联 | — |

### 现象

1. 失败任务的卡片菜单与抽屉头部提供「移至就绪」（`kanban-styles.ts:11` 原为 `failed: ['ready', 'archived']`），而服务端守卫在 `move_orchestrator.py` 里拒绝手动移出终态（`task.is_terminal and target_status != ARCHIVED`），点了只会得到 409。能把 FAILED 拉回来的只有仅供 Agent 使用的 `kanban_retry_task` 工具：人没有入口，重置、READY 流转与审计事件的实现也只存在于工具与分发器两处。
2. 把卡片拖到服务端必然拒绝的列（终态任务拖到归档以外的任何列、草稿池任务拖到执行中、IN_REVIEW 的进出等）要等请求回来才失败，提示直接显示服务端原文；多选拖拽则逐个报同样的错。
3. 归档与批量归档没有确认，归档后任务离开看板，界面里没有恢复入口。
4. 确认对话框的描述含用户任务标题，标题是无空格长串时撑破对话框。
5. 剪贴板读取授权的桌面端对话框、浏览器端 `confirm`、结论删除确认三处写死中文。
6. 批量操作栏的「移至」把就绪 / 阻塞 / 已完成写死在菜单里：选中的全是失败 / 已完成 / 审核中任务时，每个选项都必败（实测 3 个失败任务批量移到就绪：`succeeded: 0, failed: 3`，错误 `Cannot move terminal task (status=failed) to ready`），界面只显示成功与失败的数量，不显示原因。

### 根因

1. 前端的「可移动状态」表与服务端守卫是两份互不知晓的拷贝；重试这件事没有共享实现，调用方只有一个 Agent 工具。
2. 前端没有镜像服务端守卫；失败提示把 `err.message` 直通 toast。
3. 归档被当作普通移动，走与其它列相同的无确认路径。
4. 对话框描述缺 `overflow-wrap:anywhere`。
5. 文案直接写在 `ask()` / `window.confirm()` 调用里。
6. 批量操作栏的请求失败分支把 `String(e)` 直通 toast；`bulk-action` 声明了没有任何界面、测试与调用方的 `reclaim`（会中止运行中的 agent）。
7. 批量操作栏是唯一没有引用 `kanban-transitions` 的状态流转入口（卡片菜单、抽屉、拖拽都已共用它），目标列表与服务端守卫各写一份。

### 修复

1. harness：`retry_failed_task` 持有重置、`FAILED→READY` 的 CAS 与 `RETRYING` 审计事件；按 store 的 `asyncio.Lock` 串行化重复提交；重置在任务仍为 FAILED 时先落库，其后才做 CAS，工作线程紧接着认领时不会被覆盖。`KanbanDispatcher.retry_task` 只在真正生效时发 `task_retrying` 并唤醒分发器；`kanban_retry_task` 委托它，工具 schema、docstring 与错误文案逐字不变。
2. server：`POST /api/v1/kanban/tasks/{id}/retry`，任务不存在返回 404，非 FAILED 的任务原样返回 200（重复提交幂等）；手动移出 FAILED 仍被拒绝，重试是唯一回路。
3. frontend：`kanban-transitions.ts` 的 `resolveMoveIntent` 镜像服务端守卫，返回 `move / retry / archive / blocked`；卡片菜单、抽屉、拖拽三条路径都经 `requestMove`，重试与归档弹确认，`failed→ready` 变成「重试」；拖拽先排除不可能的目标并给本地化提示（只有 `deps_unmet` 用专门文案，其它一律通用文案，不再显示服务端原文）；批量归档用与批量删除一致的行内确认；`ConfirmDialog` 描述加 `wrap-anywhere`；批量操作栏加 `whitespace-nowrap` 与子项不收缩，窄屏下整条横向滚动而不是把按钮文字竖排。
4. 三处写死中文的对话框改走 i18n；`ConclusionAttributionStudioCard` 里无调用方的 `cascade` 参数及其「级联模式」措辞一并移除，并去掉其中一处原生 emoji。6 个语言包同步新增键。
5. 确认文案与实际行为一致：重试确认写明「失败后已继续推进的下游任务不会重新执行」（失败即放行依赖它的 BACKLOG 任务，见 `dispatcher_failure.py` 的失败收尾）；归档确认直接写明任务无法恢复（服务端与界面都没有恢复已归档任务的路径）。
6. 批量操作栏请求失败时显示本地化提示并保留选中（复用 `updateError`），不再显示原始异常；`bulk-action` 移除 `reclaim`，会中止运行中 agent 的动作只保留带确认的单任务入口；`TestBulkAction` 迁入独立的 `test_bulk_action_api.py`。
7. 批量操作栏的「移至」改用 `kanban-transitions` 导出的 `isServerMoveAllowed` 过滤目标：只隐藏对整个选择必然全部失败的目标，仍有任务能到达的目标保留（混合选择继续由服务端逐条返回部分成功，`test_bulk_partial_failure` 钉住这条契约）；选中任务全为终态 / 审核态时整个入口隐藏；选中任务查不到状态时不过滤。没有新增接口、文案键或服务端改动。

### 验证

1. 测试：harness `tests/toolkits/kanban/test_retry.py` 18 例通过（含「失败已放行的下游任务不被重跑」READY / RUNNING / COMPLETED 三种）；server `tests/api/kanban/test_retry_api.py` 10 例通过；frontend 新增 `kanban-transitions`、`useKanbanDnDBlocking`、`KanbanTaskDrawerMove`、`KanbanBulkActionBar`、`KanbanBoardView`、`confirm-dialog` 六个测试文件并修改既有相关测试。最后一次受影响目录的 vitest：165 个文件、1636 例全部通过（此前整库一次：1393 个文件、9868 例通过）。
2. 变异检查：拿掉拖拽预拦截与确认闸门，19 例失败；拿掉看板对 `requestMove` 的接线，4 例失败；两次均已还原并比对。
3. 真实 Chrome（生产构建，隔离输出目录，模拟接口复现服务端守卫语义；覆盖桌面浅色与深色、375px 深色、中文与英文，不是全部组合）：失败卡片菜单变为「任务详情 / 重试 / 归档 / 删除」；重试确认后实际发出 `POST /kanban/tasks/{id}/retry`（不是 `/move`），卡片离开失败列进入就绪列并出现成功提示；取消不发任何请求；抽屉头部「重试」关闭抽屉后弹出同一个确认并发出同一个请求；失败卡片拖到执行中弹出「该任务不能移到该状态」且没有请求，拖到就绪弹出重试确认，已完成卡片拖到就绪同样被拦；就绪卡片拖入失败仍走原终态确认。归档确认里的 140 多字符无空格标题在 375px 对话框内换行，对话框与文档均无横向溢出；编译产物含 `.wrap-anywhere{overflow-wrap:anywhere}`。批量归档行内确认在 1440px 下全部按钮可点击（仅末尾「取消选择」图标被全局悬浮入口遮住），375px 下「确认 / 取消」位于操作条可见区域内（但整条被悬浮入口部分遮挡，见局限）。英文下重试确认、归档确认与拖拽拦截提示正常显示，没有缺失键。
4. 静态：改动文件 oxlint 与 prettier 干净；`tsc` 仅剩他人未提交文件 `KanbanTaskHandoffSection.test.tsx(68,3)` 的一处错误；harness 改动文件的 ruff / mypy 干净，行数闸门基线已更新。
5. 批量条清理：`test_bulk_action_api.py` 12 例通过；前端 kanban 目录 22 个文件、306 例通过；两条新用例在改动前均失败（后端 `reclaim` 返回 200 而非 400；前端本地化提示未被调用）。
6. 批量条移动目标：先写失败用例，改动前 4 例失败（三种全终态 / 审核态选择仍显示「移至」，混合选择仍显示必败目标）；改完后 `components/features/kanban` 22 个文件、392 例全部通过；`kanban-transitions.test.ts` 把 `isServerMoveAllowed` 对 72 个起止状态对和 7 个「原地不动」状态逐一钉住（后者用真实守卫逐个求值：已完成、失败、审核中、草稿池移到自己当前状态被拒，归档到归档放行）；改动文件 oxlint 与 prettier 干净，`tsc` 仍只剩他人未提交文件 `KanbanTaskHandoffSection.test.tsx` 的一处错误。没有在真实浏览器里复核这一条（只有 jsdom 组件测试）。
7. 局限：
   - 浏览器复核用的是模拟接口，不是真实服务端与真实模型；重试后任务真正被认领执行的链路由 harness 与 server 测试覆盖，没有在真实桌面部署上端到端跑过。
   - 批量条不提供「重试」：失败任务只能逐个重试。没有任何真实使用数据支撑批量恢复的需求（本地库里的看板全是测试看板），而批量重试会让每个任务获得全新的重试预算并再次消耗模型额度，需要新的接口动作、确认文案和 6 个语言包，不满足投入产出；同类产品里只有 hermes 有批量恢复（把阻塞任务批量改回就绪），且它没有终态失败。
   - OSS CI 使用 PyPI 固定的 `myrm-agent-harness==0.1.0rc5`，server 新路由要在 CI 里生效，需要先发布 harness 并执行 `./myrm harness sync-lock`（独立的维护者发布步骤，本次未做）。
   - `ConclusionAttributionStudioCard` 只本地化了删除确认，其余约 50 处写死中文仍在。
   - 窄屏下批量操作栏与全局悬浮入口（小莫中枢、设计师之眼等）在底部重叠，且多选只能靠 Ctrl / Cmd / Shift 点击，触屏无法选择；均为原有问题，未动。
   - 当前工作区里他人未提交的 `move_orchestrator.py` 交接（handoff）改动使 `tests/api/kanban/test_kanban_api.py::TestSyntheticRun::test_move_with_result_and_metadata` 失败（断言 `metadata.handoff` 只含 `changed_files`，现多了 `summary`、`timestamp`），与本条无关。

### 踩坑经验

1. 前后端各存一份「允许的流转」时，只要有一份没跟上，界面就会提供一个必然失败的动作；前端镜像服务端守卫并用同一张用例表测，比等服务端报错再翻译错误更便宜。
2. 面向用户的失败提示不要透传服务端原文：只对有专门语义的错误码（如依赖未满足）给专门文案，其余统一通用文案，细节留在日志里。
3. 把重试这种「重置 + 状态转移 + 审计」收成一份共享实现，调用方（Agent 工具、REST、GUI）才不会各漏一步；先在任务仍为 FAILED 时落库再做 CAS，避免与紧接着认领的工作线程互相覆盖。
4. 模拟接口只模拟真实形状：这次复核里应用两次掉进全局错误边界，原因都是模拟接口给某些列表字段返回了对象，不是被验证的代码；排查时先看崩溃栈落在谁的组件里，再决定要不要改被测代码。
5. 浏览器自动化里 `click` 会等页面空闲，页面有持续动画或重连时可能一直超时；改用聚焦加键盘（也是真实的输入路径）可以绕开，而不是改成合成点击。
6. 服务端守卫不特判「原地不动」：终态、草稿池、审核态任务移到自己当前的状态同样被拒。过滤移动目标时把「已在该状态」一律算作可达会让全是已完成任务的选择仍显示「移至已完成」，这是先写测试才暴露的；判定要用真实守卫逐个求值，不要凭直觉。
7. 过滤批量目标要区分「整个选择必然全部失败」与「部分任务失败」：前者隐藏，后者保留，因为批量接口的契约就是逐条返回、允许部分成功；用「任一任务不可达就隐藏」会把原本能成功的那部分也禁掉。

---

## BUG-AGENT-2026-10-14-022: 「安全清空」只有接口、设置里没有任何入口，用户无法自己清空全部会话；接口也不看有没有会话正在运行

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（清空会话的入口缺失；运行中清空造成的竞争没有复现，守卫来自读代码） |
| 影响范围 | server：`app/services/system/vault_purge_service.py`（`VaultPurgeBusyError`）、`app/api/health/router.py`（409）、`tests/architecture/data/route_consumer_baseline.txt`（移除该路由）；frontend：`src/services/conversationPurge.ts`、`DataFlowErasureStrip.tsx`、`DataFlowDisclosurePanel.tsx`、6 个 locale；brand：`competitor-comparison.mdx`（中英） |
| 出现次数 | 1（读代码 + 红灯测试确认；未在真实浏览器里点过界面） |
| 关联 | `BUG-AGENT-2026-10-14-020`（清空时的逐会话拆除）、`BUG-AGENT-2026-10-14-017`（该路由已受认证保护） |

### 现象

1. `POST /health/database/safe-purge` 在路由消费者基线里登记为没有前端调用方（`route_consumer_baseline.txt` 原第 54 行）。「数据流向与隐私披露」里「您的数据权利」只有导出与记忆管理两个动作，用户想清空自己的会话只能直接调接口。
2. `SafeVaultPurgeService.purge_vault` 取到清空互斥锁后不看网关里有没有仍在运行的一轮对话，任何带认证的调用方都能在对话进行中清空。

### 根因

接口先于界面落地，基线把「没有调用方」登记成了既成事实；清空与运行中的会话之间没有任何约定。

### 修复

1. server：`purge_vault` 取锁后立即检查 `get_agent_gateway().active_session_ids()`，非空抛 `VaultPurgeBusyError`，此时尚未碰任何状态；路由映射为 409（与 `rewind` 的 `SessionBusyError` → 409 一致）；`purge_sandboxes` 的参数描述改成真实行为。
2. frontend：`conversationPurge.ts`（超时 300 s，409 映射为 `ConversationPurgeBusyError`）；`DataFlowErasureStrip` 放在「您的数据权利」下方：二次确认说明保留项（记忆、智能体、API 密钥、渠道设置）→ 调用 → 成功后清空侧栏会话缓存；确认对话框的触发按钮保持挂载（键盘焦点留在原处），结果写进常驻的实时区域，并给出「新对话」按钮（复用 `chat.newChat`，整页跳转，丢弃内存里已被删除的当前会话）；运行中与其它失败各给可重试提示，不抛出；文案沿用记忆管理界面的用词（待确认记忆、最近记忆活动），不写「本设备」；六种语言文案齐全。
3. 基线移除该路由；brand 文档补上运行中拒绝与设置入口，并把测试数改成实际值。

### 验证

1. server `tests/api/health/test_safe_purge.py` 4 例（新增 2 例：运行中拒绝，真实 SQLite 里的会话行原样、`clear_runtime_caches` 未被调用；API 层返回 409 且消息含运行数）。红灯：先是 ImportError，补上类型后 API 返回 500 而不是 409；变异（去掉运行检查）使 2 例失败，还原后通过。`tests/api/health tests/services/system tests/services/chat/test_chat_disposal.py` 共 94 例通过。
2. frontend `DataFlowErasureStrip.test.tsx` 5 例（展示说明、取消不清空、成功时的计数 / 侧栏缓存 / 焦点留在触发按钮 / 新对话入口、运行中拒绝、通用失败；实时区域在初始与失败时为空）+ `conversationPurge.test.ts` 3 例；5 个变异（不清侧栏缓存、运行中错误当成通用失败、新建会话无动作、服务层 409 映射失效、成功计数写死 0）各被 1 例杀死，还原后 8 例通过；对话框随成功结果卸载的旧实现上，探针测得 `document.activeElement` 为 `<body>`，焦点与预挂载实时区域两个红灯测试在组件改写后转绿；`system` 与 `services/__tests__` 两个目录 105 个文件 850 例通过。
3. 静态：server 三个文件 `ruff check` / `ruff format` / mypy 无问题；frontend 新文件 prettier / oxlint 干净，`verify:icu-syntax`、`verify:theme-colors` 通过，`verify:i18n` 的 6 语言完整性通过（引用检查的 59 个缺键与本条无关）。
4. 局限：运行检查是快照，清空窗口内新开的一轮不会被拦住；只覆盖网关登记的会话，cron / 看板 / IM 渠道 / 评测的 agent 运行不经网关，不在其内；客户端 300 s 超时后服务端可能仍在清空；500 可能是部分清空（数据库事务是原子的，之前的状态清理与之后的文件删除是尽力而为）；界面没有在真实浏览器里验证（浏览器工具拒绝 E2E 地址，需走 `./myrm test` 的 E2E 通道，未运行）。

### 踩坑经验

1. 路由消费者基线只收缩不扩张：补上调用方后要同步删掉基线行，否则 `test_baseline_only_shrinks` 会提示该行已不再是孤儿；
2. `ConfirmDialog` 对 `onConfirm` 抛出的错误只写 console，用户看不到原因，所以需要用户看到的失败要在回调里自己处理并给提示，而不是抛出；
3. 对话框的触发按钮不能随成功结果一起卸载：条件渲染掉它，键盘焦点会落到 `<body>`（探针实测）；结果提示用常驻挂载的 `<output>`，内容变化才会被读屏播报；
4. 面向用户的文案先查现有界面的叫法（本条的「待确认记忆」「最近记忆活动」取自记忆管理界面），并避免绑定部署形态的措辞（「本设备」在托管部署下不成立）。

---

## BUG-AGENT-2026-10-14-023: 归档技能后已打开的会话仍带着它；后台学习的技能被人工批准后，系统写的英文审核备注进了技能的 description；一次自动学习弹两条提示且没有撤销；成长卡片把扫描器与运行时原文直接印给用户

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（数据正确性：技能描述被污染并进入每轮的技能目录；归档不对热会话生效；其余为 P3） |
| 影响范围 | server：`app/core/skills/curator/service.py`（`apply_skill_archived`、`run_curator_sweep`）、`app/api/skills/drafts.py`、`app/services/skills/{auto_extractor,draft_notification,evolution_events}.py`、`skills/growth/{lifecycle,queries}.py`；frontend：`hooks/globalEvents/skillGrowthToasts.ts`（新增）、`useGlobalEvents.ts`、`services/skill/growth.ts`、`SkillHistoryPanel.tsx`、`lib/skills/growthReason.ts`（新增）、`components/features/skills/growth-card/`（新增 `GrowthTechnicalDetails.tsx`）、六种语言文案；各目录 `_ARCH.md` 与根 `ARCHITECTURE.md` |
| 出现次数 | 1（读代码 + 红灯测试确认；未在真实浏览器与真实 LLM 里跑过） |
| 关联 | `BUG-AGENT-2026-10-14-018`（本条补上它记录的局限之一：扫描发现的 `description` 与应用失败的 `remediation` 原文未本地化；它记录的「没做浏览器级别视觉检查」仍未补上）；本地提交，未 push |

### 现象

1. 归档或恢复技能后，已经打开过的会话下一轮仍用旧的技能目录：执行缓存的指纹包含 `skill_config_version`（`execution_cache/fingerprint.py:210`），指纹相等就直接复用已构建的 agent（`registry.py:119`），而归档的唯一写入口 `apply_skill_archived` 不推进这个版本；
2. 后台学习的草稿因「相似技能 / 扫描失败 / 进化锁 / 应用失败」落成待审，系统把英文备注拼进记录的 `reason`；用户人工批准时，`draft.description`（即这段 `reason`）被原样写进新技能的 SKILL.md frontmatter，备注因此成了技能描述，并出现在每一轮进入模型的技能目录里；
3. 自动落地一个新技能时，`skill_evolved` 与 `skill_growth_updated(AUTO_APPLIED)` 各弹一条 toast，两条都没有撤销入口；
4. 成长卡片里扫描器的英文描述、运行时的错误签名与循环类型、应用失败原文直接展示；「相似技能 / 扫描未过 / 进化锁」这几类原因只存在于上面那段英文备注里，卡片没有本地化说明；
5. `auto_extract_skill` 里有一条永远走不到的补丁分支：后台复盘产出的补丁一律走人工审核；
6. 用户撤销（归档）一个自动学到的技能后，同名技能再次被提议时落成待审；人工批准会重写 SKILL.md，但生命周期状态仍是已归档，技能被批准了却不会被加载，界面没有任何提示；
7. Curator 的 sweep 归档技能后不推进配置版本，已打开的会话继续带着被归档的技能；
8. 可选进化的回滚（`skill_evolved` 提示里的撤销）用裸 `fetch` 调 `/api/v1/evolution/{id}/rollback`，不带 `Authorization` 头，也绕过本机后端就绪检查；开启令牌鉴权的部署里这个撤销会失败，只显示「撤销失败」。

### 根因

1. 归档写入口只改了技能的生命周期状态，没有通知「技能配置已变」这个缓存键；
2. 「给人看的审核原因」与「会成为技能内容的描述」共用了同一个字段（`reason`）；
3. 两个事件各自带提示，没有约定谁负责提示；又不能简单地让所有 `skill_evolved` 静默，因为人工批准草稿时发的也是这个事件，而前端对「已批准」状态没有提示；
4. 服务端只下发了拼好的英文，没有下发稳定的原因码，展示层无从本地化；
5. 补丁分支是 P1 改成「补丁一律人审」之前遗留的；
6. 草稿落盘只写文件，不看同名技能当前的生命周期状态；
7. sweep 的归档由 Harness 的 Curator 引擎直接写状态，服务层没有在其后通知缓存键；
8. 回滚没有服务层封装，提示代码直接拼 URL 调 `fetch`，另一处历史面板用的是 `apiRequest`，两处走了不同的请求入口。

### 修复

1. `apply_skill_archived` 写入后调用 `bump_skill_config_version()`，归档、恢复、修复、成长时间线四个调用方共用这一处，热会话下一轮重建；被拒绝的归档（固定或被绑定）不推进版本；
2. 审核原因改为结构化原因码：`risk:<信号>` / `similar:<技能名列表>` / `scan_failed` / `evolution_locked` / `apply_failed`（常量在 `draft_notification.py`），应用失败原文存 `apply_error`，扫描摘要存 `security_scan_summary`；`description` 始终是纯技能描述；`evaluate_growth_scan` 返回 `(描述, 扫描摘要)`，不再往描述里追加文字；
3. `publish_skill_evolved_event` 增加 `notify`，后台自动落地传 `False`（由成长事件提示），人工批准与可选进化保持默认 `True`；前端 `skillGrowthToasts.ts` 只在 `notify === false` 时跳过提示，同时仍派发 `skill-evolved` 供界面刷新；
4. 自动落地的提示只弹一条，带「撤销」= 归档（`PATCH /skills/curator/{name}/lifecycle`，可在技能列表恢复）；固定或被绑定时服务端返回 409，用单独文案说明，其他失败用通用文案；该提示改用「Agent 学会了新技能」的措辞，删除不再使用的 `skillGrowthAutoApplied`；
5. 前端新增 `lib/skills/growthReason.ts`（封闭词表解析 `similar:` / `scan_failed` / `evolution_locked`，词表外返回 null）；`GrowthCaseEvidence` 按原因码给出本地化的「为什么需要你审核」，应用失败只给本地化结论；扫描器描述、运行时错误签名与循环类型、应用失败原文与服务端建议统一收进默认收起的 `GrowthTechnicalDetails`；六种语言新增对应文案，删除不再使用的 `runtimeFailure.loopKind`；
6. 删除 `auto_extract_skill` 的补丁分支，传入非 `skill_draft` 类型直接返回 `unsupported result_type`；
7. `drafts.py::_materialize_skill_draft` 落盘成功后，若同名技能处于已归档状态，经 `set_skill_archived(..., archived=False)` 恢复：批准草稿就是用户决定让它运行；
8. `run_curator_sweep` 在 `archived_count > 0` 时推进配置版本；
9. 新增 `services/skill/growth.ts::rollbackSkillEvolution`（`apiRequest`，带鉴权头），提示与历史面板共用，删除裸 `fetch`；
10. `useScanRiskText.ts` 的翻译器绑定去掉类型注解：`verify:i18n` 的引用门禁此前对 `scanRiskText.ts` 报 6 条键缺失，原因是门禁只认 `const t = useTranslations(...)`，认不出 `const t: ScanRiskTranslate = ...`，键实际都在 `settings.skills.scanRisk`；去掉注解后该门禁不再报这 6 条；
11. `drafts.py` 里两处已有的 pyright 类型错误（`eval_cases` 收窄、`_TEST_MOCK_DRAFT_NAMES` 的元组长度）一并修掉；`undoEvolve` 在中文、繁体中文、日文里去掉「(Undo)」后缀，与其余语言一致。

### 验证

1. 服务端：`tests/api/skills`、`tests/core/skills`、`tests/services/skills`、`tests/api/evolution`、`tests/integration/skills` 与 `tests/architecture` 分两次跑：第一次（`-x`，排除他人改动的 `test_curator.py`）747 通过后在 `test_prebuilt_skills_e2e.py` 停下；第二次 `tests/architecture` + `tests/integration/skills` 2095 通过、16 失败，其中 13 例是 `tests/architecture` 的他人改动（路由消费者、服务域词表、`__init__.py` 布局、前端 API 路径、server 对 harness 的深层导入；`test_frontend_api_literals_target_existing_routes` 的违规清单里没有本条新增的 `/evolution/{}/rollback`），3 例是 `test_prebuilt_skills_e2e.py`（失败日志出自 `app/core/skills/store/service.py:352` 的「Runtime load excluded … (disabled)」，该文件有他人未提交改动，`gates/runtime_load.py` 是他人新增的未跟踪文件；本条没有改这些文件，单独跑该文件同样失败 3 例）；本条涉及的全部文件 `ruff check` / `ruff format` / `pyright` 无问题；同目录其余文件另有 7 条 ruff、10 个未格式化、72 条 pyright 报错（`app/{api,core,services}/skills` 下 22 个文件，多数是他人正在改的文件），没有动；
2. 前端：全量 vitest 1398 个文件 9919 例，9917 通过、2 失败（`stageTaskCount.test.ts`、`taskTopologyModel.test.ts`：子代理拓扑「待审节点」的断言，他人的改动）；新增 `skillGrowthToasts.test.ts` 11 例、`growthReason.test.ts` 12 例，并在 `SkillGrowthCaseCard.scanRisk.test.tsx` 补了原因码、应用失败、运行时失败、技术细节折叠的用例；本条涉及文件 `oxlint`、`prettier`、fractal 文档检查通过；`tsc --noEmit` 只剩他人的 `KanbanTaskHandoffSection.test.tsx(68,3)`；`bun run lint` 仍有 `verify:stable-mocks`、`verify:a11y`、`verify:hardcoded-copy` 三个门禁失败，报出的文件（agent-assembler、channels、chat/group、system-monitor 等）都是他人的，本条涉及文件不在其中；`verify:i18n` 还剩 53 条键缺失，全部在他人的 chat / kanban / `SkillDetailSheetContent`；`useGlobalEvents.ts` 由 716 行降到 674 行，行数基线没有新增本条的项；
3. 变异验证：去掉 `bump_skill_config_version()`、跳过 `notify` 判断、把 409 判断改成 500、撤销改成恢复、卡片直出 `applyError`、技术细节里去掉扫描器描述、`scan_failed` 解析失效，共 7 处，各被 1 例杀死，还原后通过；第 6、7 条各有红灯测试（去掉修复后失败：批准后状态仍为 `archived`、sweep 归档后版本仍为 0.0），修复后通过；第 8 条的单测改为断言经 `rollbackSkillEvolution` 调用，裸 `fetch` 的缺陷由 `apiRequest` 带 `Authorization` 头的代码（`lib/api.ts:436-446`）确认，没有开令牌鉴权的真实部署验证；
4. 局限：没有在真实浏览器里看过（深浅主题、375px 宽度）：ChromeAgent 拒绝了 `localhost:3000`（`CHROME_AGENT_E2E_URL_REJECTED`），需要走 `./myrm test -m chrome_e2e` 通道，未运行，当前只有 jsdom 渲染测试与语义色 / 主题色门禁（`verify:theme-colors` 通过）；没有用真实 LLM 端到端跑过后台复盘；「归档后热会话下一轮不再带该技能」由指纹与缓存复用的代码链路加版本推进的单测推出，没有开真实对话验证；已经在库里的待审记录保留旧的带备注描述（不迁移，数量受上限约束且会被处理掉）；撤销自动落地的技能后，对应成长卡片的状态仍显示「已自动落地」；自动学到的技能默认带进化锁，Curator 的自动淘汰对它们不生效，所以 sweep 归档的版本推进只对用户自建、未加锁的技能有意义；复盘提示词没有改动，也没有评估其对产出质量的影响。

### 踩坑经验

1. `apiRequest` 把 HTTP 状态码放在 `ApiError.code`（`lib/api.ts:515`），用状态码区分 409 与其他失败时直接比较它，不要解析消息文案；
2. 事件的「提示」与「刷新」要分开：静默掉整类事件会让共用该事件的另一条路径失去反馈，需要显式的 `notify` 标志；
3. zsh 不会对未加引号的变量按空格拆词，`FILES="a b"` 再传给 `ruff` 会被当成一个路径；要用数组 `FILES=(a b)` 与 `"${FILES[@]}"`；
4. 用 `Intl` 之外的方式拼名称列表时，技能名受 `SKILL_NAME_PATTERN` 约束不含逗号，才能用逗号当分隔符，这个前提要在解析处写明。

---

## BUG-AGENT-2026-10-14-024: 风控闸门对带占位词、引用或查询串的赋值仍然拦下，对带环境变量前缀的真密钥与 13 种厂商前缀放行；规则与命中记录的 `action` 字段恒为 `block`，却留在库、接口、种子和每次启动的归一化里

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P2（误拦会让用户关掉规则，漏拦让真密钥进模型；`action` 是死字段，没有用户可见的后果，但每次启动多两次写库、接口与种子多一个无意义字段） |
| 影响范围 | server：`app/services/risk/{constants,patterns,builtin_rules,builtin_business_rules,match_checks,detection,rule_service}.py`、`app/api/risk/{router,schemas}.py`、`app/lifecycle/risk_rules.py`、`app/database/{models/security,migrations}.py`、`app/services/security/profile_manager.py`（只改类型）；harness：`core/security/detection/{secret_value,leak_detector}.py` |
| 出现次数 | 1（复审 `BUG-AGENT-2026-10-14-019` 时逐条验证发现；没有真实用户聊天数据） |
| 关联 | `BUG-AGENT-2026-10-14-019`（本条修它留下的误拦、漏拦与表述过满的数字）· harness `BUG-HARNESS-2026-10-14-022` |

### 现象

1. 在测试清单上（55 条应放行、64 条应拦下；清单是照着下面这些问题写的回归清单，不是独立抽样），019 之后的 HEAD 误拦 7 条：`?api_key=YOUR_KEY&k=1&sig=Zk9mango42`（值一路读过 `&k=`）、`secret: isSecret（N3）`（值读进全角括号）、`password: YourSecurePassword123!` 与 `SECRET_KEY=CHANGE-TO-A-UNIQUE-64-CHAR-SECRET-KEY`（文档里让读者填的占位）、`postgres://app:${DB_PASSWORD}@db:5432/app`、`postgres://user:<password>@host/db`、`postgres://user:password@localhost/db`（连接串规则不看密码是引用还是词）；漏拦 16 条：`GROQ_API_KEY=gsk_…`、`DB_PASSWORD=…`、`aws_secret_access_key = …`（键前面的 `_` 是词字符，`\b` 找不到键）和 hf_、r8_、pplx-、gsk_、dop_v1_、sbp_、npm_、pypi-、SG.、tvly-、bb_live_、shpat_、shpss_ 共 13 种厂商前缀（闸门自己存的前缀清单比 harness 的表短）。新代码在同一清单上误拦 0、漏拦 0。
2. 真实文件语料（`external_reference_project` 里按固定种子取的 300 个文档与 300 个源码文件，472 万字符；只是这一份抽样）：HEAD 17 个文件命中，新代码 12 个，没有新增命中，清掉 5 个（`python-scaffold` 技能、三份 crewAI 文档、`modal/references/secrets.md`）。
3. 规则与命中记录各有一个 `action` 列，值只会是 `block`：种子 31 条各写一遍，API 请求与响应带它，`RiskMatch` 带它，每次启动还跑 `disable_non_block_rules` 与 `clear_stored_match_text` 两次写库归一化，而没有任何读取方按它做分支。
4. 019 条目里有两处数字写得过满：“拦下 28/28”和“5/600”是挑出来的清单与一份抽样上的结果，不是对一般文本的误报率与召回率。

### 根因

1. 赋值规则的值是 `[^\s"']+`，只在空白与引号处结束，所以它会读过 `&k=` 与全角标点；占位只靠通用的“引用/词/掩码”判断，文档占位不在其中；`db_connection_string` 没有命中后的确认。
2. 键起点用 `\b`，`_` 与字母同属词字符，环境变量前缀的键永远不匹配。
3. 厂商前缀密钥的清单在闸门里存了一份，harness 的 `leak_detector` 又存了一份，两份各自增删，闸门那份落后 13 种。
4. `process.env.GROQ_API_KEY!` 的 TypeScript 非空断言不在 harness 的引用判断里。
5. `action` 是 `allow` 被删之后留下的单值字段，019 只把取值收窄到 `block`，没有删字段。

### 修复

1. server `match_checks._assigns_secret`：先把值截到它自己的范围（下一个 `&k=`、第一个非 ASCII 标点），再交 harness `secret_value_span`，并拒绝以 `your` / `change` / `replace` / `example` / `placeholder` / `dummy` / `sample` / `insert` / `enter` 开头的占位值：任何大小写下，词在分隔符或结尾处结束；驼峰写法则在下一个大写字母处结束；词后面接着别的字母的是密码本身（`Yourdog2012!`、`Enterprise2012x`、`ENTERPRISE2012!` 都仍被拦）；`db_connection_string` 的 pattern 捕获密码为 `value`，纳入同一确认。
2. `patterns.KEY_START`（`(?<![A-Za-z0-9])`）取代 `\b`：`DB_PASSWORD`、`GROQ_API_KEY`、`aws_secret_access_key` 的键能被认出；`credential_assignment` 与 `env_file_secret` 使用它。
3. `API_KEY_PATTERN` 由闸门自己的 `sk-` 形状加 harness `DISTINCTIVE_KEY_PATTERNS`（24 种）拼成，不再另存清单；`vercel_`、`fal_` 等会命中标识符的弱前缀不在其中；`test_builtin_rule_precision.py` 要求表里每种形状都有样本且被拦下，表新增形状而没有样本时失败。
4. harness `is_reference_value` 认三段以上属性链结尾的 `!`（`process.env.GROQ_API_KEY!`；两段的 `john.smith!` 仍可能是密码），见 harness 条目。
5. 删除 `action`：种子、两个模型列、API 字段、`RiskAction`、`RiskMatch` 与编译后规则里的字段、`rule_service` 的校验；两个启动归一化改成迁移（先把非 `block` 的规则停用，再 `DROP COLUMN` 两次，再清空旧摘要里的原文），启动不再多两次写库。
6. 019 条目里过满的数字补上样本限定；`_ARCH.md`、`tests/_ARCH.md` 的对应描述与 harness `redact/patterns.py` 的“单一来源”说法改准确；`server_harness_import_baseline.txt` 补上 019 起就缺的三个条目（`card_context`、`pii_patterns`、`secret_value`）。

### 验证

1. 同一份测试清单、同一个真实规则引擎，HEAD 与新代码对照：应放行 55 条，HEAD 误拦 7、新 0；应拦下 64 条，HEAD 漏 16、新 0。HEAD 一侧用的是现在的 harness（已含 `!` 的判断），所以 `process.env.X!` 两条在 HEAD 一侧也放行。
2. 变异验证 6 处，各被 1 例杀死，还原后通过：不截值、不认占位词、连接串不看密码、键起点改回 `\b`、不用 harness 的表、非 ASCII 符号也截（`password: p@ss€word42` 被截成 `p@ss` 放行）。
3. 测试：风控、生命周期、数据库迁移、渠道闸门与 bus 相关 361 例通过（含新增的迁移测试：旧库的 `action` 列被删、非 `block` 规则被停用、旧摘要原文被清空、新库迁移幂等；新增的 API 测试：规则与命中不带 `action`、仍带 `action` 的旧客户端请求不被拒）；harness `tests/core/security` 1127 例通过（复审后增加 1 例，现为 1128 例）；server 的 `ruff` 与风控文件的 `mypy` 无新增问题，harness `ruff`、`mypy` 通过。
4. 更宽的回归：`tests/channels`、`tests/core/channel_bridge`、`tests/api/channels` 7530 通过、14 失败；其中 3 例是本条漏改的 `test_bus.py`（`RiskMatch(action=…)`，已修，单文件 55 例通过），其余 11 例与 019 记录的他人改动同族（群路由 6、前缀触发 1、`btw` 命令 2、日志脱敏 1、译文孤键 1），没有逐例复核原因，也没有改它们。`tests/architecture` 13 例失败（路由调用者基线、API 与服务域词表、`services/workflow` 缺 `__init__.py`、前端 API 路径、harness 导入基线里他人新增的深层导入），不涉及风控代码。
5. 耗时（每条消息过 8 条默认规则，取 5 次最小值，HEAD 与新代码同一台机器同一批文本）：2 千字符聊天 0.26 → 0.41 毫秒；36 万字符日志 4.7 → 11.2 毫秒；36 万字符 `a.a.` 串 72 → 93 毫秒；36 万字符全是 `password = input() ` 的文本 166 → 196 毫秒（`credential_assignment` 单条 132 → 141 毫秒，距 0.25 秒的单条时限不远；时限只约束正则扫描，不约束命中后的确认循环）。
6. 提交后的复审：全大写的占位词前缀见“踩坑”第 1 条。修正后 3 个新增的全大写应拦用例通过；把旧正则写回去，这 3 例失败、其余通过，还原后全部通过。整个 `external_reference_project`（约 110 万个文件）里，以全大写占位词开头、没有分隔符的赋值值只有 `CHANGEME`、`YOURSECRETACCESSKEY`、`YOURACCESSTOKEN`、`REPLACEMENT_TEST_RELAY_KEY`、`CHANGEME_*_PASSWORD` 这类，逐个过闸门都放行（纯字母或下划线词，本来就不算密钥），所以收紧没有在这份语料里带来新命中。同一批文本、同一台机器、取 5 次最小值，上一提交 → 当前：2 千字符聊天 0.24 → 0.34 毫秒；36 万字符、含大量 `token` 与 `id=` 的日志 43.6 → 60.4 毫秒；36 万字符 `a.a.` 串 72 → 93–101 毫秒（两轮测量）；36 万字符 `password = input() ` 164 → 195 毫秒。这份日志与上面第 5 条的不是同一份文本，数字不能互相比较。
7. 同一轮把 `SecurityProfile.config_json` 的类型从裸 `dict` 改成 `dict[str, object]`（模块里原有的 `mypy` 错误），连带去掉 `profile_manager` 里一处不再需要的 `type: ignore`，换成 `cast`；`_serialize_config` 先做 JSON 往返，不改入参，所以去掉原来的 `dict(...)` 拷贝行为不变。`mypy` 对这两个文件与风控文件无错误，`tests/services/security`、风控、迁移与生命周期共 171 例通过。复审后重跑：`tests/services/risk`、迁移、生命周期、渠道 bus 与入站闸门（6 个文件集合）共 233 例通过；第 3 条的 361 例集合更大，没有原样重跑，两个数字不能互相对比。

### 局限

1. 抽样里剩下的 12 个命中：2 个是文档在讲 PEM 头本身，2 个是文档示例（`Bearer token123`、`sk-litellm-virtual-key-abc123`），3 个是 `sessionId: 'session-123'` 一类会话标识，1 个是 `sessionId: entry!.sessionId`（`!` 在链中间，本条只认链尾的 `!`），1 个是 `apiKey: items.mem0ApiKey`（带数字的标识符链被当成可能的密钥），1 个是字符串里字面的 `API_KEY=secret\n#…`，2 个是测试里的假密钥。
2. 同族问题没有覆盖：`process.env.X!.trim()` 仍被拦；密码里含 `&x=` 的会在那里被截断；以占位词加分隔符开头的真密码（`Your_Pass_2024!`）会放行；纯字母的连接串密码（`postgres://admin:hunter@db`）会放行，与赋值规则“精度优先”的口径一致，HEAD 上这类写法被拦；全角冒号的 `password：…` 与中文键名（`密码`）不被规则识别（原有）。
3. 键起点从 `\b` 改成“不是字母数字”之后，`user_token: abc123def456` 这类带前缀的键开始被检查；抽样没有新增命中，真实聊天里的误拦率未知。
4. 019 起带 `action` 的旧导出文件：字段被忽略，规则按启用的拦截规则导入。
5. 不带标签、单独贴出的 Databricks（`dapi…`）、Twilio（`SK…`）、Firecrawl（`fc-…`）、Vercel、Cloudflare、ElevenLabs、fal、Telegram 机器人与 Discord 机器人令牌不被闸门拦下：这 9 种形状在 harness 里属于弱前缀，不在 `DISTINCTIVE_KEY_PATTERNS` 里；带 `api_key=` 一类的标签时会被赋值规则拦下。在整个参考语料里，这 9 种形状中的 4 种（Telegram、Discord、Twilio、Databricks）扫到 22 处（其余 5 种没有扫）：14 处是 Telegram 文档占位（`123456789:XXXX…`），3 处是 `dapi0123456789abcdef…` 示例，5 处形似 Discord 的有 4 个是 Swift 驼峰标识符，另 1 个是令牌形状的字符串（没有查它的出处），Twilio 为 0 处；没有一处能确认是真令牌，所以把它们放进拒绝级会误拦文档与代码。代价是这些真令牌不带标签直接粘贴时不被拦（上一提交同样不拦，没有退步）。
6. 规则编辑器的测试面板（`detect_preview`，`detection.py:206-219`）只跑模式本身，不做命中后的确认，所以对内置赋值规则，面板会列出闸门并不拦下的 `password = input()`；与闸门在这一点上口径不同（原有）。
7. 全大写、没有分隔符的占位词加数字（`YOURPASSWORD1`、`ENTERPASSWORD1`）会被拦，因为词后面接着字母，与 `ENTERPRISE2012!` 无法区分；纯字母的（`CHANGEME`、`YOURPASSWORD`）不受影响。
5. 回滚：旧版服务在已迁移的库上播种内置规则会因没有 `action` 列写库失败，之后风控没有规则、不拦任何消息；升级后不要回退。
6. `secret_value_span` 与 `DISTINCTIVE_KEY_PATTERNS` 都不在 harness 已发布的标签里，服务端仍钉 `==0.1.0rc5`，发布 harness 并执行 `./myrm harness sync-lock` 之前 OSS 的锁定安装无法导入；发版由维护者执行，本次没有执行。没有在真实渠道与浏览器里端到端验证；提示词没有改动。

### 踩坑经验

1. 全局 `(?i)` 下，占位词清单会把 `Yourdog2012!`、`Changeme2024!` 当占位；改用作用域内的 `(?i:…)`。这一步还不够：`(?i:enter)(?=[A-Z])` 里的“下一个字符是大写”对全大写的 `ENTERPRISE2012!` 同样成立（词已吃掉 `ENTER`，下一个是 `P`），于是 `ENTERPRISE2012!`、`SAMPLER99xyz`、`YOURMOM1234x` 被当成占位放行。清单里只有首字母大写的写法，361 例看不出来；交付后的第二轮复审逐个构造全大写值才发现。现在分隔符与结尾不分大小写，驼峰（`[Yy]our` 这类首字母可大可小、其余小写）才看“下一个是大写”。
2. 曾想用“全大写短横线串就是占位”，但 `API_SECRET=ABCD-EFGH-IJKL-9999` 是真密钥的形状，所以用词表而不是形状。
3. 600 个文件的抽样里看不到 `vercel_`、`fal_` 对标识符的误拦；整个语料用 `rg -P` 扫出约 3.5 万处，所以它们进了弱前缀表。抽样看不到不等于不存在。
4. `KEY_START` 起初写成 `(?:(?<![A-Za-z0-9])|(?<=[_-]))`，第二支是第一支的子集（`_` 与 `-` 本来就不是字母数字），多余，且在病态文本上让 `credential_assignment` 慢了一倍；改成单个后行断言后 `a.a.` 串上从 39 毫秒降到 31 毫秒，仍比 HEAD 的 20 毫秒慢。
5. 第一版对非 ASCII 的标点和符号都截断，复审时发现 `p@ss€word42` 会被截成 `p@ss` 而放行，改为只截标点并加了用例。
6. 删字段时只搜了风控目录，漏了 `tests/channels/test_bus.py` 里三处 `RiskMatch(action=…)`，跑渠道全量时才暴露：删字段要对全仓搜构造点，不能只看模块目录。

---

---

## BUG-AGENT-2026-10-14-025: 永久删除与「安全清空」各按一份手写表清单拆除会话数据：拼错的表名让小组件存储被静默跳过，有未保存改动的沙箱工作树与未合并分支被强制删除；无凭据的 GET 能触发数据库从备份恢复；资源检查与启动参数里还有无人调用、或被忽略的开关

| 属性 | 值 |
|------|------|
| 发现日期 | 2026-10-14 |
| 修复日期 | 2026-10-14 |
| 严重程度 | P1（清空与永久删除会丢掉用户没有保存的工作；匿名 GET 触发的恢复只在 SQLite 自检失败时才会执行，没有构造损坏库端到端复现，路径来自读代码） |
| 影响范围 | server：`app/services/chat/{chat_bound_rows,chat_crud,chat_disposal,sandbox_worktree}.py`、`app/services/system/vault_purge_service.py`、`app/services/infra/sandbox_cleanup.py`、`app/core/utils/git_worktree.py`、`app/core/security/auth/public_paths.py`、`app/api/health/router.py`、`app/core/infra/health/{coordinator,sqlite}.py`、`app/startup/*`、`run.py`；frontend：`conversationPurge.ts`、`DataFlowErasureStrip.tsx`、6 个 locale；harness：`utils/db/fts5.py`、`api/__init__.py`；brand：`competitor-comparison.mdx`（中英） |
| 出现次数 | 1（复审 `BUG-AGENT-2026-10-14-020` / `-022` 时逐条验证发现；真实 SQLite 与真实 git 仓库复现，没有用户数据） |
| 关联 | `BUG-AGENT-2026-10-14-017`（公开路径按前缀放行，本条把 GET 收窄到探针）· `-020`（会话拆除）· `-022`（清空入口）· harness `BUG-HARNESS-2026-10-14-023` |

### 现象

1. 「安全清空」按一份手写的表清单删会话绑定的数据，清单里把 `widget_kv` 写成 `widget_kv_entries`；删除函数对不存在的表只记一行忽略，所以小组件存储从来没被清空，清空后接口仍报成功。`approvals`、`commitments`、`fission_task_records` 同样靠 `chat_id` / `source_chat_id` 绑定会话，单个永久删除与清空回收站只处理 `widget_kv`，这三张表在两条路径上都没人清，安全清空也没有。
2. 永久删除、清空回收站、安全清空对沙箱都用强制清理：工作树里有未提交的改动，也有只存在于该分支上的未合并提交，两者都被删掉；界面与接口不会告诉用户有什么被保留或丢失。
3. 安全清空在事件循环里同步清理工件保险库（临时目录里 500 个会话 × 10 个工件加 5 000 个全局对象，停顿 1 937 ms），期间所有请求排队。
4. `/api/v1/health` 前缀下的 GET 全部无需凭据：doctor、info、metrics、resources、pressure、update-status、browser 等诊断都对匿名者开放，并跳过 Host 白名单；其中 `GET /health/resources?auto_recover=true` 会让 SQLite 检查器在自检失败时隔离当前库并从最近备份恢复。该参数没有任何调用方（前端、控制平面、脚本都没有）。
5. `force_recovery` 贯穿 `run.py`、两个启动器、启动检查、协调器、`SQLiteHealthChecker` 与上述路由，描述是「允许删除 SQLite WAL」，实际在检查器里被忽略；`purge_vault` 的 `purge_memories` / `purge_sandboxes` / `reclaim_disk` 三个开关无人传入非默认值。
6. harness 的 `safe_purge_fts5_virtual_table` 没有任何生产调用方，只靠自己的测试和一条门面导出存活，而 server 的文件头与三份文档把清库里的 FTS5 清理说成它做的；`StorageVaultBackend.backup_corrupted` 用 `str.replace(".enc", ".corrupted")`，域名里含 `.enc`（如 `mail.enc.example.com`）时两处都被改写。

### 根因

1. 「哪些表绑定了会话」没有单一来源：清空、单个永久删除、清空回收站各存一份，没有任何测试对着真实库的表结构核对。
2. 清理沙箱的 `force=True` 来自「用户已明确丢弃」的假设，但这三个入口丢弃的是会话，不是工作树里的改动。
3. 公开路径用前缀，探针与诊断被放在同一个前缀下；`auto_recover` 是启动检查的参数，被原样暴露成了查询参数。
4. 开关先于需求落地，调用方一直没出现，也没人删。

### 修复

1. `chat_bound_rows.py`：`CHAT_BOUND_TABLES` 是唯一注册表（`widget_kv`、`approvals`、`commitments`、`fission_task_records`），清空逐项遍历、单个永久删除与清空回收站调用 `delete_trashed_chat_bound_rows`；后者每条 DELETE 都带「该会话仍在回收站」的 EXISTS 条件，过期的 id 列表不会误删已恢复会话的数据，按 500 个一批。守卫测试要求真实库里每张带会话列的表必须登记、或写明由别的路径清除、或写明有意保留（及理由）。
2. 沙箱：`cleanup_sandbox_worktree(force=False)` 保留有未保存改动的工作树，并且只用 `git branch -d` 删分支，有未合并提交就保留；`remove_chat_files` 返回 `ChatFilesRemoval(removed_worktrees, kept_worktrees)`，安全清空的结果与接口多一个 `kept_sandboxes`，清空条在 `kept_sandboxes > 0` 时多一行说明（6 种语言），确认文案补一句保留规则。只有「关闭沙箱」接口与合并后的清理仍然强制。
3. 工件保险库清理改在 `asyncio.to_thread` 里跑，同一批数据实测事件循环停顿 1 937 ms → 16 ms。
4. `public_paths`：只读公开路径改为三个精确路径 `/api/v1/health`、`/liveness`、`/ready`，其余健康端点走正常准入与 Host 白名单；`/health/resources` 变成只读（`auto_recover=False`，不再接受任何恢复参数，返回里去掉 `auto_recover` / `force_recovery` / `recovery`）。`/health/metrics` 的文档字符串原写「需要管理员权限」，实际只要求通过准入，已改成实情。
5. 删除 `force_recovery` 整条链与对应测试，删除 `purge_vault` 的三个开关；启动期的 `--no-auto-recovery` 保留。
6. harness 删除 `safe_purge_fts5_virtual_table`、只服务于它的 `ConnectionLike` 协议、门面导出与测试，brand 两份与 temp-docs 一份文档改成「清库事务里逐表发送 `delete-all` / `rebuild` / `optimize`」；`backup_corrupted` 改成只换结尾的 `.enc`。

### 验证

1. 红灯 / 变异：清单里写错表名 → 清空测试失败；去掉守卫测试的分类 → 失败；沙箱分支用 `-D` 的旧行为 → 新增的 3 个真实 git 仓库用例失败；把公开规则改回前缀 → 25 个用例失败；`/resources` 改回 `auto_recover=True` → 对应用例失败；`.enc` 用 `replace` → 新增用例失败；工件清理改回同步 → 事件循环用例失败。每个变异还原后全部通过。
2. 新增 / 重写：`test_chat_bound_rows.py` 4 例（表存在、分类守卫、只删回收站里的、超过 500 个 id）、`test_safe_vault_purge_service.py` 10 例（真实全量表结构）、`test_chat_disposal.py` 18 例、`test_sandbox_worktree_integration.py` 7 例、`test_sandbox_cleanup_batch.py` 4 例、`test_safe_purge.py` 3 例、`test_resources.py` 3 例、`test_public_paths.py` 165 例、`test_auth_middleware.py` 7 例（远程模式：探针匿名可达，doctor 无密钥 401、有密钥 200）；前端 `DataFlowErasureStrip.test.tsx` 6 例。
3. 扫描：server `tests/services/{chat,system,infra} tests/api/{health,chats} tests/middleware tests/core/{security,infra} tests/unit tests/database` 1 812 例通过，5 例失败均来自他人未提交的工作（`test_aux_llm_privacy` 4 例、`test_storage_governance_api`：`app/services/instance_archive/` 尚未跟踪）；`tests/architecture` 13 例失败，均为他人在途改动（路由消费者基线、harness 深层导入基线、前端 API 路径）；harness `tests/utils tests/api` 与会话保险库测试通过，仅 `test_token_tracker` 1 例失败（他人在途）；harness `boundary_check`、`check_fractal_docs`、`check_import_resolvability`、`check_test_source_assertions` 通过。
4. 局限：
   - 安全清空的运行检查只看网关登记的会话；cron / 看板 / IM 渠道 / 评测的运行与已脱离的子代理不经网关。统计它们的 `app/core/agent/run_activity.py` 还是未跟踪的他人工作，没有接入。
   - 健康诊断端点改为需要准入后，前端里 8 个组件用相对路径的裸 `fetch`（`ResourcePressureBanner`、`UpdateNudgeBanner`、`StackUpdatePanel`、`AboutSection`、`useTrayStatus`、`BrowserPoolCard`、`BrowserDoctorCard`、`MemoryMonitorCard`）依赖浏览器自带的会话 cookie；远程 WebUI 的会话 cookie、沙箱控制平面代理签名、手机配对页三种准入下它们的真实行为没有实测，只核对了代码与调用点。
   - 被保留的工作树没有界面入口可以移除（接口在，界面没有调用）；有未合并提交的分支被保留时不会提示。清理过程中抛异常的会话也按「保留」计数。
   - `empty_trash` 在预读之后才进回收站的会话仍有既有的竞争窗口。
   - 永久删除与清空回收站原先被 `_ARCH.md` 定义为「明确丢弃」（`force=True`），现改为保留有未保存改动的沙箱，文档已同步。

### 踩坑经验

1. 对「哪些表属于某个实体」这类事实，写成单一注册表，再用真实库的表结构做一次反向核对；手写清单加「表不存在就忽略」会把拼写错误变成静默跳过；
2. 对同一批会话 id 的删除要带「仍在回收站」条件：别处可能已恢复其中一个，过期的 id 列表不是授权；
3. 同一个前缀下既有探针又有诊断和运维动作时，按精确路径放行，并让「放行清单里的每一项都是真实的 GET 路由」成为测试，清单才不会悄悄过期；
4. 暴露给 HTTP 的参数不要直接复用启动期的恢复开关：恢复会改库，读接口不应该能触发；
5. 做公开面收窄前先列出每个调用点的凭据来源（`apiRequest` 带 Bearer 与配对头，裸 `fetch` 只带 cookie），再决定能不能收。

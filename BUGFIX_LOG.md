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
4. 模型页订阅卡片的提示与 toast 用 `locale === 'zh' ? … : …` 分支，日、韩、德、繁体中文用户只能看到英文。

### 根因

1. 订阅令牌存放在一条加密 blob 里，没有清理遗留发行方的步骤；`oauth_refresher.py` 里 Copilot 的非标刷新、`oauth_store.py` 的 Copilot 基础地址解析、`config_loader.py` 的发行方映射、前端的三个订阅入口与 PKCE 重开页都是这三条登录的专属代码，随登录一起成为死代码；
2. 预检横幅直接渲染服务端返回的发行方标识 `i.issuer`，没有使用已有的 `formatOAuthIssuerLabel`；该函数只做首字母大写，`xai` 只能得到 `Xai`（品牌拼写是 xAI）；`getOAuthIssuerSettingsPath` 还靠 `provider_` 前缀把订阅发行方指向模型页，三条登录下线后这个分支成了死代码；
3. 副标题与卡片文案没有进 `locales`，违反「所有写死文案进 locales、六语言」的项目规范。

### 修复

1. server：`provider_oauth.py` 收敛为 xAI 门面（`/xai/start`、`/xai/poll` 委托 `xai_oauth.py`，共用 `/status/{provider}`、`/disconnect/{provider}`，以及仅本地模式的测试种子 / 清理端点）；删除 `oauth_refresher.py` 的 Copilot 刷新分支与 `COPILOT_ISSUER`、`oauth_store.py` 的 `extract_copilot_base_url`；`config_loader._PROVIDER_OAUTH_MAP` 只剩 `xai`（`provider_xai` 别名没有任何写入方：xAI 凭据一直写在发行方 `xai` 下）；`push_deep_links.py` 的 OAuth 重新授权统一落到 `/settings/credentials`；删除 Anthropic 订阅策略诊断探针；
2. server：新增 `retired_provider_oauth_purge.py`，启动期在共享行锁内删除三个遗留发行方——没有遗留项时不写回，无法解析的 blob 不覆盖，重复执行结果相同；`lifespan.py` 在数据库就绪后调用，失败只记 warning、不阻塞启动；
3. frontend：`provider-oauth.ts`、`ProviderOAuthSection.tsx`、`NoProviderBanner.tsx` 收敛为 xAI（首启弹窗只剩一个订阅入口）；订阅卡片文案进 `settings.modelService.oauth`（六语言）；
4. frontend：`integrationOAuthDisplay.ts` 的 `formatOAuthIssuerLabel` 增加品牌名表（用 `Map`，以免 `constructor` 这类标识命中原型属性），删除 `getOAuthIssuerSettingsPath` 与 `provider_` 前缀，OAuth 重新授权落点统一为 `SETTINGS_CREDENTIALS_PATH`（`reauthToasts.ts`、`DataFlowDisclosurePanel.tsx`、`getIntegrationSkillSettingsPath` 同步）；预检横幅改用 `formatOAuthIssuerLabel` 渲染并补上两串之间的分隔；
5. frontend：六个中心的 17 条副标题搬进六语言 `locales`（`settings.{developerCenter,systemCenter,memoryCenter,toolQualityCenter,modelCenter}.tabDescriptions.*`、`settings.skills.tabSubtitles.*`），组件改用 `useTranslations`，「API 秘钥」改为「API 密钥」；删除六语言里已退役的 `chat.subscriptionCopilot / Openai / Claude / PkceNotice / PkceReopen` 与 `i18n-shell-allowlist.json` 里对应条目。

### 验证

1. 清理逻辑的变异检查：`test_retired_provider_oauth_purge.py` 7 例在原实现下全绿；逐个应用 4 个变异（用抛弃式 pytest 插件在解释器内改写模块源码，项目文件不动）：遗留列表恒为空 → 3 红；把 `xai` 也列入遗留 → 5 红；去掉「无遗留项不写回」的提前返回 → 2 红（密文变化证明发生了重写，无法解析的 blob 被覆盖）；只写回不删除 → 3 红；锚点不存在时插件直接报错，证明改写确实生效；
2. 前端：对订阅卡片、首启弹窗、预检横幅、发行方展示名、重新授权 toast、数据流披露面板逐个做变异检查（约 25 个，均先红后绿，用抛弃式 vitest 配置，项目文件不动）；副标题新增 `centerSubtitles.test.tsx`：直接读六语言 `locales/*.json`，对 17 条副标题断言单语言（无「中文 / English」混排、英德无 CJK、其余语言含 CJK 且不等于英文），并以真实目录解析（缺失路径即抛错）渲染六个中心的每个标签页、六种语言共 132 例；对它应用 3 个变异（映射到不存在的 key、两个标签文案互换、key 拼错）分别 6、12、6 例变红；
3. server：受影响的两批共 227 个用例通过（`web_push`、设置深链架构测试、`provider_oauth` 接口、`config_loader`、`model_resolver_enrich`、清理逻辑；OAuth 刷新 / 存储 / 会话凭据 / 诊断 / lifespan 等）；其中 `test_oauth_reauth_sse.py` 的 1 例因他人把 `_EVENT_TEMPLATES` 从 `dispatcher.py` 挪到 `adaptive_cards.py` 而早已红，把导入改到新位置后该文件单独复跑 3 例通过；`ruff check`、`ruff format --check` 对触及的服务端文件通过；
4. frontend：11 个相关测试文件 355 例全绿；受影响目录的广域扫描 360 个文件 2215 例中 2213 例通过（见下方局限）；`verify-i18n.mjs`（含全量 key 对齐、占位符、翻译壳、双语对照、纯净门禁）、`prettier --check`、oxlint、`verify:stable-mocks`（本次触及的文件）通过，全量 `tsc --noEmit` 只剩他人 `KanbanTaskHandoffSection.test.tsx` 的 1 条类型错误；
5. 局限：没有真实订阅账号与真实浏览器，xAI 设备码授权的端到端流程没有重新跑过，只有单元测试与前端交互测试；对 mypy 报告里落在 `oauth_store.py`、`oauth_refresher.py`、`server_diagnostics.py` 的既有报错，确认与本次改动的行不重叠，但没有在 HEAD 基线上单独比对错误数；pyright 在本机解析不到 `sqlalchemy`，结果无效。

### 踩坑经验

1. 删登录只删代码不够：令牌存在加密 blob 里，必须同时有启动期的幂等清理，并且要证明两件事——不会清掉还在用的发行方（`xai`、`google_workspace`），也不会改写没有遗留项的 blob 或覆盖无法解析的 blob（加密每次写入用新的随机数，密文不变即证明没有重写）；
2. 变异检查要覆盖「清得太多」与「写得太多」两个方向，只测「清掉了」会放过把现役发行方也清掉的实现；
3. 前端测试里 mock `next-intl` 的 `t` 必须是稳定引用（`verify:stable-mocks` 会拦），按命名空间缓存同一个函数；
4. 局限（已核实、未处理，不属于本次范围）：`NoProviderBanner` 的启动授权失败路径先 `setActiveFlow(null)` 再用 `setActiveFlow((prev) => prev ? … : null)` 写错误，错误永远写不进去，用户看不到失败原因；授权轮询返回的 `pollRes.error` 与异常的 `err.message` 会原样展示给用户；预检横幅只缺 MCP 时点击落在 `/settings/skills`，而 `getIntegrationSkillSettingsPath` 对 MCP 给的是 `/settings/agents#loadout`；IM 通知模板 `adaptive_cards.py` 的 OAuth 重新授权文案写「Settings → Integrations」，设置菜单里没有这一项（凭据页叫 Credentials）；`tests/api/integrations/test_mcp_registry_api.py` 有两例依赖线上 Smithery 网络；`MemoryGuardianCard.test.tsx` 的 1 例在受影响目录扫描里失败（单独运行同样失败，渲染停在骨架屏，源文件与测试均未被本次改动）；`BuiltinToolsPanel.kanban.test.tsx` 的 1 例在满载的扫描里超时，单独运行通过。

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

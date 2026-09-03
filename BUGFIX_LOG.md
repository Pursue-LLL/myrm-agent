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

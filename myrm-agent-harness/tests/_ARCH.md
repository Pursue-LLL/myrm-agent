# tests/

## Overview

Harness test suite: unit, integration, architecture gates, and performance benchmarks. Default execution is serial (`-n0`) with a memory-safe marker filter in `pyproject.toml` `addopts`.

## File & Submodule Index

| Path | Role | Description |
|------|------|-------------|
| `__init__.py` | 核心 | tests 包标记（pytest 收集根） |
| `conftest.py` | 核心 | 全局 pytest 配置：隔离 `MYRM_DATA_DIR`、`outside_tmp_path` 夹具（`/var/tmp` 下的临时目录，供"未加白名单即被拦截"类断言使用，因为校验器恒放行 `/tmp` 而 Linux 的 `tmp_path` 位于其下）、进程级状态隔离自动夹具（审批拒绝计数、会话 executor stash、`chat_id_var`、动态 MCP 安全元数据注册表、context 污点追踪器、已发布的 active tool registry/resolved tools、子代理 checkpointer 单例、CLI 工具探测缓存）、blocking_io gate、benchmark→performance 标记、浏览器 xdist 串行组、`pytest_collection_finish` warmup/acquire_page 漏标门禁、浏览器测试目录，或池内仍有存活浏览器/launcher 的测试，在夹具收尾调用 `reset_global_browser_pool_for_tests()`（带 30s 超时，超时则丢弃单例）；sessionfinish 浏览器进程树 cleanup（`tests/support/browser_process_cleanup`） |
| `fixtures/` | 辅助 | 预留 harness-only 夹具目录 · [fixtures/_ARCH.md](fixtures/_ARCH.md) |
| `examples/` | 辅助 | 非 shipping 参考实现 · [examples/_ARCH.md](examples/_ARCH.md) |
| `mocks/` | 辅助 | 共享 in-memory backend mock · [mocks/_ARCH.md](mocks/_ARCH.md) |
| `support/` | 辅助 | pytest teardown helpers（browser 进程树 cleanup）与真实 MCP 传输测试辅助（live server / TLS PKI / launch-gate stub）· [support/_ARCH.md](support/_ARCH.md) |
| `backends/` | 单元 | 存储后端（profiles/secrets/skills）· [backends/_ARCH.md](backends/_ARCH.md) |
| `scripts/` | 单元 | `scripts/` 维护脚本单测（tool registry）· [scripts/_ARCH.md](scripts/_ARCH.md) |
| `features/` | 单元 | Feature Flag 引擎 · [features/_ARCH.md](features/_ARCH.md) |
| `performance/` | 性能 | 子进程 import 热点与 lazy-loading 回归、MCP 并行连接守卫（`test_mcp_connect_perf.py`，真实 stdio 子进程；`mcp_connect_bench.py` 可对 HEAD 导出做同口径基线对比）（`performance` marker） |
| `toolkits/` | 单元/集成 | 镜像 `src/.../toolkits/<name>/`；禁止空壳目录 · [toolkits/_ARCH.md](toolkits/_ARCH.md) |
| `architecture/` | 门禁 | 边界与打包一致性检测 — 见 [architecture/_ARCH.md](architecture/_ARCH.md) |
| `eval/` | 单元 | Eval 框架断言/runner/reporter · [eval/_ARCH.md](eval/_ARCH.md) |
| `observability/` | 单元 | 顶层 metrics/diagnostics/tracing · [observability/_ARCH.md](observability/_ARCH.md) |
| `agent/streaming/broadcast/` | 单元 | ToolBroadcastBus / ToolCallBroadcaster · [agent/streaming/broadcast/_ARCH.md](agent/streaming/broadcast/_ARCH.md) |
| `integration/` | 集成 | 跨模块集成（含浏览器 wait-strategies 等） |
| `agent/skills/curator/test_curator_engine.py` | 单元 | SkillCurator 生命周期与豁免规则（勿用通用名 `test_engine.py`，会与 `agent/dynamic_workflow/test_engine.py` 触发 collect import mismatch） |
| `agent/skills/` | 单元 | 技能子系统测试树 · [agent/skills/_ARCH.md](agent/skills/_ARCH.md) |
| `agent/_factory/test_mcp_routing_route.py` | 单元 | `route_mcp_servers` direct/PTC/aggregate demotion + compress 边界（mock connection） |
| `agent/_factory/test_builder_compactor.py` | 单元 | `create_skill_agent` 上下文管道辅助压缩模型 `summarizer_llm` 注入装配 |
| `agent/_factory/test_mcp_routing_real_stdio_integration.py` | 集成 | 真实 MCPServer stdio **160 tools**（超过 11250 token 阈值）→ PTC/Skill 路径（无 mock） |
| `agent/meta_tools/skill_search/test_engine_mcp_index.py` | 单元 | MCP skill BM25 index enrichment（>3 tools） |
| `agent/meta_tools/skill_manage/` | 单元 | `skill_manage_tool` 并发锁语义（同用户同技能串行、不同技能/用户并行、出错后释放；经批次入参）· 批次运行器的快照来源（快照读取器优先于轮次后端，缺省回退）、patch 的读取来源（先读写入侧存储：轮次后端看不到的技能也能 patch，且改的正是写入侧将要覆盖的正文；该存储没有的技能回退轮次后端）与删除终局（删除批次不调提交 hook、结果无批次 id/脚注/撤销提示，中英各一条）· lock/unlock 的批次语义（不进快照、文件操作全部成功后才执行；操作失败或持久化 hook 失败时各锁恢复到批次前状态，包括「已加锁再 lock」不被误解锁；只含 lock 的批次无撤销记录；混合批次的提示说明撤销不含锁，中英各一条；结果按列出顺序；工具描述向模型说明锁何时落地与撤销范围，中英各一条）· 共享假件 `batch_fakes.py`（假提交 hook、假写入后端、假读取器） |
| `agent/skills/evolution/` | 单元 | Skill evolution pipeline tests (incl. trace analyzer takeover, variant generator, the engine working from the SKILL.md on disk) |
| `agent/errors/diagnostics/test_diagnostic_result_single_source.py` | 门禁 | AST：`DiagnosticResult(` 只在 `diagnostics/catalog_result.py` 构造（含别名与模块属性调用，且该构建器必须仍在构造；检测器自证 sample 防退化为 no-op）；`dataclasses.replace` 复制不算构造，不被拦 |
| `agent/errors/diagnostics/test_transport_exception_chain.py` | 单元 | 连接失败沿异常链读取证书被拒：按 litellm 实际的六层链构造（外层隐式 `__context__`、内层 `raise ... from`），只有最内层带原因；带硬证书信号 → `tls_certificate`（自定义端点同样，而不是 `custom_endpoint_unreachable`）；拒绝连接、域名无法解析、`wrong version number`、`Broken pipe` 仍是连接类；外层是限流、认证、超时的异常不被链改写 |
| `agent/errors/diagnostics/test_enterprise_network_card_copy.py` | 门禁 | 两张 TLS 卡（证书被拒、握手中断）的末步都指向企业网络兼容设置，六种语言的目录都说明改后需重启应用（各语言一个关键词），且两张卡的末步逐字相同；语言表与已发布的目录文件集合相等，新增语言而不补词会变红 |
| `integration/test_enterprise_tls_compat_integration.py` | 集成 | 企业网络兼容设置对真实客户端栈生效：本机 https 监听口的证书链按 TLS 检查代理的形状签发（CA 的 `basicConstraints` 未标关键，严格 OpenSSL 拒绝），产品聊天模型（`create_litellm_model` + `ainvoke`，经 litellm 的 aiohttp 传输）与 `create_httpx_client` 各一遍；默认、只开设置不给 CA、只给 CA 不开设置都被拒且归为证书被拒，开设置并经 `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` / `NODE_EXTRA_CA_CERTS` 之一给出 CA 才放行；开了设置，过期证书与主机名不符的证书仍被拒；显式钉死的 CA 只信那一个；用例前预先建好 litellm 的默认上下文（它在被导入时就建好，早于宿主读到设置），所以不丢弃缓存的实现会让聊天模型用例变红；监听口与干净状态来自 `support/tls_loopback.py` |
| `integration/test_enterprise_tls_entrypoints_integration.py` | 集成 | 同一设置对不经 httpx 的客户端库生效：`urllib.request`、`http.client`、aiohttp 默认会话、`requests`（各从不同入口取上下文：`ssl._create_default_https_context`、aiohttp 导入时建好的默认上下文、urllib3 自己的构造函数），面对同一条按 TLS 检查代理形状签发的证书链；默认、只开设置不给 CA、只给 CA 不开设置都被拒（沿异常链找到标准库的证书校验失败），开设置并经 `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` / `NODE_EXTRA_CA_CERTS` 之一给出 CA 才放行；开了设置，过期证书与主机名不符的证书仍被拒；`requests` 另测显式 `verify=` CA 文件与经本机 `CONNECT` 代理两条路径；标准库客户端在设置关回去后新建的上下文不再放宽 |
| `integration/test_tls_certificate_rejection_integration.py` | 集成 | 真实 litellm 客户端栈对一个本机监听口（证书由客户端不信任的私有 CA 签发）发起 https 调用，openai / anthropic / gemini / ollama_chat / deepseek 五个供应商族各一次：失败分类为 `TLS_CERTIFICATE`、诊断为 `tls_certificate`（各族客户端层把同一次证书被拒包装成不同形状，手工构造的异常链防不住这种漂移）；对照组是回纯 HTTP 的监听口，仍是 `TIMEOUT` 且不判证书被拒（https 打到纯 HTTP 服务仍按瞬时传输故障重试）；证书材料复用 `tests/support/mcp_testkit/tls_pki.py`；各族客户端的异常链长不得超过读取上限的一半，在多一层客户端封装把根因挤出读取范围之前就报警；聊天模型每次调用都会把端点写在 litellm 模块上且不还原，用例前先清掉，否则同进程里排在它之后的 ollama_chat 直接调用会打到上一个用例的端点 |
| `toolkits/llms/test_tls_rejection.py` | 单元 | 证书被拒的统一判定，按手工构造的异常链：硬证书信号、被「Connection error.」封装的根因、`ssl.SSLCertVerificationError` 类型本身（操作系统以自己的语言措辞时没有 OpenSSL 文字可匹配；同一句话挂在非验证类型的异常上不判；只复述原因的外层照读，声明了其他结论的外层——限流、密钥被拒、超时——保持自己的结论）、不含证书的连接失败仍是瞬时故障；4xx 应答即使正文引用了证书报错也不判证书被拒，网关转发的 5xx 仍判；根因在链深上限内都能读到、超出上限则读不到；该原因永久、可切换、按超时节奏探测 |
| `infra/test_tls_compat.py` | 单元 | 企业网络兼容的上下文策略，标准库与 httpx 一侧：开关值解析；安装只在关闭严格时发生且不重复包装；默认上下文信任系统证书库且验证保持开启；环境变量给出的 CA 追加信任、不可读或缺失的文件跳过并告警；显式 CA 文件或数据保持原样信任；服务端用途不动；系统证书库不可用时退回标准信任；开关关回去后新上下文不再放宽；安装后 `httpx.create_ssl_context` 取系统证书库；`create_httpx_client` 透传参数；硬证书与瞬时握手信号表；夹具与上下文探查辅助来自 `infra/conftest.py` 与 `support/tls_context_probe.py` |
| `infra/test_tls_compat_libraries.py` | 单元 | 同一策略在各第三方库一侧：urllib3 的构造函数与它实例化的上下文类都带上策略（系统证书库、环境 CA、去严格标志），持有构造函数的每个 urllib3 模块都被改绑、包外的同名绑定不动；`urllib.request` / `http.client` 用的 https 默认入口指向策略，宿主自己替换过的不动；aiohttp 默认上下文重建，aiohttp 未导入时不去导入，缺少内部构造函数时告警不报错；各库被策略伸手进去的内部（aiohttp 默认上下文与构造函数、urllib3 的类与构造函数、标准库 https 默认入口、litellm 上下文缓存）各有契约用例，发布改动它们时先红 |

## Test file placement

The `tests/` root holds only `__init__.py`, `conftest.py` and `_ARCH.md`. Every test file lives in the subtree that mirrors the `src/myrm_agent_harness/` module it covers (for example `agent/context_management/`, `toolkits/memory/`, `agent/tool_management/`); never add `test_*.py` directly under `tests/`. One test module covers one source domain: split a module that spans two (for example eviction marks and memory consolidation) instead of naming it `test_<a>_and_<b>.py`. The root rule is enforced by `scripts/check_package_root_layout.py` (CI boundary job) and `tests/architecture/test_package_root_flat_layout.py`.

## Test file naming

Duplicate basenames such as `test_engine.py` under different `tests/agent/**` subtrees can trigger pytest `import file mismatch` during collection. Use domain-specific names (e.g. `test_curator_engine.py`).

Real Chromium tests under `tests/toolkits/browser/` must carry `integration` or `e2e` (or `performance`). `pytest_collection_finish` fails collection if a test function calls `.warmup(` or `.acquire_page(` without those markers.

## Test execution (memory-safe)

| Profile | Command | Notes |
|---------|---------|-------|
| Monorepo default | `./myrm test -n0 <path>`（open-perplexity 根） | monorepo 内统一走 `./myrm test`，不裸跑 `uv run pytest`；CI 用 `uv run --no-sync`；harness gate 自愈 editable |
| Monorepo integration | `./myrm test -m integration <path>` | 默认 addopts 排除 integration |
| Local default (harness-only) | `pytest` (addopts apply filter automatically) | Serial; ~300–500MB typical peak (darwin arm64, 2026-06) |
| Full suite | `pytest -m ""` | All markers including integration/e2e/performance |
| Browser integration | `pytest -m "integration or e2e" --timeout=600` | Real Chromium; run separately |
| CI unit | `.github/workflows/harness-test.yml` job `unit` | `uv sync --python 3.13 --locked --extra all --group dev`, then `uv run --no-sync pytest -n 2` over the whole `tests/` tree with the default marker filter; a stale `uv.lock` fails the install step (run `uv lock` after editing `pyproject.toml`; `compiled-core*` exclusion: `harness_packaging/DISTRIBUTION_SYSTEM.md` § CI) |
| CI performance | `.github/workflows/harness-performance.yml` | `uv sync --python 3.13 --locked --extra all`, then `tests/performance/ -m performance -n0` |
| CI browser | `.github/workflows/harness-test.yml` job `browser-integration` | Same install; `-n0`, `-m "integration or e2e"`, Patchright Chromium (`--with-deps`) |
| CI CLI contract | `.github/workflows/harness-cli-contract.yml` | Weekly + manual; same install, the latest real `claude` / `codex` from npm, then `-m integration` over `tests/toolkits/acp/runtime/cli/test_real_cli_contract.py`, `test_real_cli_failures.py` and `test_real_cli_images.py` (a local stub API refuses or answers the requests: no login, no network, no model billed). Other jobs skip these tests because the CLIs are not installed |

## Browser integration pitfalls（实测经验，2026-08）

1. **pytest-asyncio loop scope 必须 pin 为 module**：`pyproject.toml` 已全局设置
   `asyncio_default_test_loop_scope = "module"` + `asyncio_default_fixture_loop_scope = "module"`。
   Browser 集成测试用 module-scoped async fixture（如 `GlobalBrowserPool.warmup`）持有 patchright
   连接，其 coroutine 绑定 fixture 所在的 event loop；若测试跑在默认 function-scoped loop 上，
   跨 loop await 会永久挂起直到 `--timeout=300` 超时。**禁止**用 `--override-ini=asyncio_default_*_loop_scope=function`
   降级此配置。

2. **`set_content` 会替换 `document.body` 节点但保留 window/document**（`document.write` 语义）。
   在 `new_tab` 阶段已被安装的 MutationObserver 会悄然观察已脱离文档的旧 body，
   `getChanges()` 永远返回空。快照链路通过 `ObserverManager.ensure_active()`
   （`observer_scripts.py` 的 `ensureActive()` 比较 `bodyRef`）在每次 capture 时自愈。
   测试里若发现 observer 失效，先检查 body 引用是否已变（探针：
   `window.__savedBody.isConnected === false` 即被替换）。

3. **本地地址测试注意 SSRF guard 与 domain_filter 叠加**：云模式下 SSRF guard（`navigation/ssrf_guard.py`）
   在 `goto` 之前按 URL 拦截私有网段（抛 `BrowserNavigationBlockedError`，当前标签页保持不变）；已装过滤器的 context
   在每个请求再次校验私有网段，拦截时浏览器侧是 `net::ERR_ABORTED`、服务端收不到请求。
   验证 domain_filter 的 allow/block 行为时须在 `BrowserSession` 显式传 `allow_private_networks=True`：
   该标志让两层只放行「会话显式导航到的私网源」（经重定向 / 脚本到别的私网地址仍被拦，云元数据永远被拦），
   名单与资源规则照常生效；`test_private_network_policy_integration.py`、
   `test_local_mode_navigation_policy_integration.py`、`test_document_redirect_integration.py`、`test_domain_lists_redirect_integration.py`（名单对重定向目标同样生效）、`test_hostname_resolution_policy_integration.py`（解析到环回 / 云元数据的主机名按该地址判定；用 `--host-resolver-rules` 把假域名映射到环回夹具，并替换进程内 `socket.getaddrinfo` 充当攻击者控制的 DNS）是端到端证据。
   重定向链由 `tests/toolkits/browser/_redirect_servers.py`（逐请求记录 `(method, path)` 的多服务器夹具）搭建，
   断言服务端收到几次请求，而不是只信浏览器侧结果（`Reply.delay_s` 模拟慢业务端点，用来证明表单 POST 在响应慢于驱动请求超时的情况下仍只提交一次；`declared_length` / `hold_open_s` 脚本化被截断或读到一半的响应；`Gated` 按请求头区分页面自己的请求与裸重发）；web_fetch 侧见 `tests/toolkits/web_fetch/test_fetch_ssrf_terminal.py`。
   并用本地 `ThreadingHTTPServer` 做真实页面源，避免外部网络依赖。**禁止**用猴子补丁替换
   `install_domain_filter` 或其他过滤器入口来"让环回可达"——那会遮住标志没有传到过滤器的缺陷。
   浏览器网络工具同法取证：`tests/toolkits/browser/session/test_network_terminal_states_integration.py`（`network_log` 如实标注重定向跳转、失败请求与页面丢弃但服务端已答复的请求，并以 Chrome 自己的 `loadingFailed` 事件作对照；`network_detail` 说明为何没有响应体；`network_replay` 只重发 GET 并回答真实状态码）、`tests/toolkits/browser/session/test_network_log_listing_integration.py`（404 的脚本以不带编号的一行列出、编号 1 仍打开 API 请求，没有任何 XHR/Fetch 的白屏页也列出该脚本；非 UTF-8 的 POST body 不丢记录）、`tests/toolkits/browser/session/test_network_log_page_scope_integration.py`（换页、刷新、切换标签页各自从头列起，`pushState` 路由切换不换页；离开的页面的失败脚本不带到下一页；页面取的图片与字体只计数不列出；上一页的编号被拒绝并给出现在有效的编号）、`tests/toolkits/browser/session/test_network_detail_long_body_integration.py`（超长响应体：vault 副本脱敏并折成不超过 200 字符的行，答复只给指针与开头，按行范围读到答复没给出的部分，服务端只被请求一次；没有 vault 时退回截断）、`tests/toolkits/browser/session/test_network_replay_bounds_integration.py`（`network_replay` 对读不完的响应体按窗口截断后即答，对中途停住的服务端到时限带着已收到的部分答复，对一直不答的服务端以错误答复；时限在测试里缩短）与 `tests/toolkits/browser/test_evaluate_write_guard_integration.py`（`evaluate` 不放行页面 JS 写请求，服务端命中数为证）；不需要定制启动参数的真实会话统一用 `tests/toolkits/browser/_local_browser_session.py::local_session`（可带 `content_vault`，让会话把长输出存进 vault）。

4. **`run_site_tool` 输出经 `mark_untrusted` 包裹**（BROWSER_SYSTEM.md 统一安全出口）。
   程序化消费必须走 `extract_wrapped_payload()` 解包后再 `json.loads`，不要直接对裸结果解析。

5. **浏览器可用性检测禁止用 `shutil.which("chromium")`**：macOS/Windows 上 patchright 管理的
   Chromium 装在 Playwright 缓存目录（`~/Library/Caches/ms-playwright` 或 `$PLAYWRIGHT_BROWSERS_PATH`），
   不在 PATH，导致 `requires_browser` 误判跳过整个浏览器池测试（曾经 31 个池/并发测试静默未跑）。
   统一走 `tests/toolkits/browser/_browser_available.py::chromium_available()`——
   它通过 patchright registry 解析真实 `executable_path` 并检查文件存在。

6. **导航摘要/Inspector 预览快照禁止污染 diff baseline**：`BrowserSession.navigate` 内部
   `_append_navigate_interactive_summary` 与 `view_update_payload.capture_browser_view_update_data`
   会用 `snapshot(diff=False, compact=True, scope="interactive")` 做只读预览。若这些调用也更新
   `SnapshotDiffEngine` baseline（`get_snapshot` 默认行为），用户导航后首次 `snapshot(diff=True)`
   就会拿到与 interactive/compact 范围对比的无效 diff。预览用途必须显式传
   `update_baseline=False`（`get_snapshot`/`BrowserSession.snapshot` 新增参数，默认 True 保持契约）。

## Key Dependencies

- `pyproject.toml` `[tool.pytest.ini_options]` markers and `addopts`
- `myrm_agent_harness.toolkits.browser.pool.singleton` (GlobalBrowserPool singleton lifecycle)

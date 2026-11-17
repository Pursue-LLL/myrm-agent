# shared/config/ 模块架构

## 架构概述

前后端共享的静态 JSON 配置。

## Normalize Contract

Legacy storage id remap 在前后端使用**同一算法**（与 [`providers.py`](../../myrm-agent-server/app/services/agent/params/model_config/providers.py) · [`providerIdentityMigration.ts`](../../myrm-agent-frontend/src/store/config/providerIdentityMigration.ts) 一致）：

1. `trim()` 首尾空白
2. `-` → `_`
3. `lower()` 小写
4. 查 `provider_legacy_remap.json`；未命中则返回 trim 后的原 id（不改大小写）

## 文件清单

| 文件 | 职责 | 消费者 |
|------|------|--------|
| `provider_legacy_remap.json` | 遗留 providerId → canonical storage id | `providers.py` · `providerIdentityMigration.ts` · Docker `/shared` · PyInstaller bundle · vitest · pytest |
| `kanban_move_guard.json` | 看板任务手动 move 的流转表：每个起点状态（含「原地不动」）服务端接受的目标状态 | [`kanban-transitions.ts`](../../myrm-agent-frontend/src/components/features/kanban/kanban-transitions.ts) 据此在发起前拦下必败的移动 · 服务端只在测试里读它，运行时不读 |
| `kanban_blocked_reasons.json` | 服务端自己拥有的看板任务阻塞原因（依赖合并失败、模型用量上限、批次暂停、工作目录过宽、运行停在审批请求上、运行停在浏览器要人的一步）的原文，按 key 命名 | [`kanbanBlockedReason.ts`](../../myrm-agent-frontend/src/lib/kanban/kanbanBlockedReason.ts) 按整句匹配译成界面语言 · 服务端只在测试里读它，运行时不读 |
| `media_generation_contract.json` | 生成媒体的结果形状与登记规则：图像模型清单、三个媒体工具的返回形状、聊天登记的条目形状，以及两端共同遵守的登记用例 | [`mediaGenerated.ts`](../../myrm-agent-frontend/src/lib/chat/mediaGenerated.ts) · [`imageModels.ts`](../../myrm-agent-frontend/src/lib/utils/media/imageModels.ts) · `ImageTaskCard` / `VideoTaskCard` 的结果解析 · 服务端 [`media_generated.py`](../../myrm-agent-server/app/services/agent/streaming_support/media_generated.py) 实现同一套登记规则，服务端只在测试里读这份文件，运行时不读 |
| `chat_input_limits.json` | 用户在聊天里输入的文字，服务端允许的最大长度（按字符计）：`history_search_query`（侧栏会话搜索、Cmd+K 消息搜索、`@chat:` 选择器、共享上下文历史搜索共用）与 `compact_focus_topic`（压缩上下文的聚焦主题） | [`chat-history-search.ts`](../../myrm-agent-frontend/src/lib/constants/chat-history-search.ts) · [`compact-focus-topic.ts`](../../myrm-agent-frontend/src/lib/constants/compact-focus-topic.ts) 据此给输入框限长、截断发出的文本 · 服务端只在测试里读它，运行时不读 |

## Kanban Blocked Reasons Contract

阻塞原因在服务端是一句英文（频道命令、诊断、活动流原样展示），看板卡片与抽屉按整句匹配成界面语言的文案，匹配不上就原样显示，
所以两边的句子必须逐字相同。`kanban_blocked_reasons.json` 是 `{key: 句子}`，key 同时是前端 `kanban.blockedReason.<key>` 的文案 key；
[`test_blocked_reason_contract.py`](../../myrm-agent-server/tests/services/kanban/test_blocked_reason_contract.py)
要求它与服务端常量完全一致。服务端新增、改动阻塞原因句子，或这张表有改动，都要让该测试保持通过，并在前端补上对应文案
（前端按这张表的 key 取文案，缺文案由前端测试拦下）。

这张表只收服务端自己拥有的原因；`batchPause` 的原文 `batch_pause` 是服务端筛选冻结任务用的标记，值不能改，所以由前端译成可读文案。
其余原因的集合是开放的——目标模式的暂停原因、预算耗尽（含轮数）、智能体自己写的原因——不在表里，界面原样显示。

## Kanban Move Guard Contract

`kanban_move_guard.json` 是 `{起点状态: [可达目标状态]}`，覆盖全部 9 个状态。服务端规则仍在
[`move_orchestrator.move_task`](../../myrm-agent-server/app/services/kanban/move_orchestrator.py)；
[`test_move_guard_contract.py`](../../myrm-agent-server/tests/api/kanban/test_move_guard_contract.py)
把 9 × 9 对状态逐对打到真实的 `POST /kanban/tasks/{id}/move`，接受与否必须和这张表完全一致。
改服务端守卫或这张表，都要让该测试保持通过。

## Media Generation Contract

媒体工具的结果由服务端产出、由前端卡片消费，聊天里的卡片又由工具结果登记出来，三处必须对同一份形状达成一致，所以形状写在 `media_generation_contract.json`：

- `image_models`：图像模型清单，顺序与 harness `BUILTIN_PROFILES` 一致；设置页的 `IMAGE_MODEL_OPTIONS` 逐项等于它。
- `shapes`：`generate_result`（`tasks[{task_id, task_type, status}]`）、`image_result`（`images[{url, mime_type}]`、`model`、`prompt`、`latency_ms`，`provider` 可选）、
  `video_result`（`video_urls`）、`speech_result`（`audio_url`、`model`、`duration_seconds` 可选）、登记条目 `task_entry` / `stored_entry`。
  图像、视频、语音地址一律是 `media://<id>`；字段类型只有 `string`（非空）、`number`、`media_reference`、`{list}` 和 `{one_of}`。
- `collector_cases`：工具名 + 结果 + 应登记的条目。服务端 `collect_media_generated` 与前端 `mediaGeneratedEntriesOf` 都逐条跑它。

[`test_media_generation_contract.py`](../../myrm-agent-server/tests/unit/ai_agents/media_tools/test_media_generation_contract.py)
把真实的生成入口、任务执行器、同步编辑、语音工具的输出逐一按 `shapes` 校验，并跑 `collector_cases`；
前端 [`mediaGenerationContract.test.ts`](../../myrm-agent-frontend/src/lib/chat/__tests__/mediaGenerationContract.test.ts) 与
[`mediaGenerationContract.test.tsx`](../../myrm-agent-frontend/src/components/features/task-card/__tests__/mediaGenerationContract.test.tsx)
用同一份文件核对登记结果、模型清单和两张任务卡片。改任一端的字段名或这份文件，都要让两条测试保持通过。

## Chat Input Limits Contract

服务端对几处用户输入设了长度上限，超过一律 HTTP 422，上限写在各自的请求模型里（`Query(max_length=…)` / `Field(max_length=…)`）。前端不知道上限，用户就会一路敲到提交才失败，
所以数字写在 `chat_input_limits.json`，输入框的限长与发出前的截断都读它。
[`test_chat_input_limits_contract.py`](../../myrm-agent-server/tests/api/chats/test_chat_input_limits_contract.py)
把每个输入逐条打到真实路由：恰好等于上限的文本不能因长度被拒，多一个字符必须是 422，JSON 里的每个上限也都得有路由对应。

上限按字符计（生僻汉字、emoji 算一个字符），浏览器的 `maxlength` 按 UTF-16 单位计，所以输入框只会更早停下，不会放行服务端拒收的文本；
发出前的截断走 [`firstChars`](../../myrm-agent-frontend/src/lib/utils/firstChars.ts)，口径与服务端一致。改服务端上限或这份文件，都要让该测试保持通过。

# approval/batch_processor/decide/

## 架构概述

逐工具判定循环，按阶段拆开：`loop.py` 的 `evaluate_calls` 对批内每个调用依次跑各阶段，第一个落定调用的阶段结束该调用的判定，结果写进 `state.py` 的 `Verdicts`（approved / denied / pending 三个列表）；没有阶段落定的调用带着 `CallState` 里累积的审批卡上下文挂起等人审批。`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 阶段顺序

1. `preflight.py`：操作符当按键名、不可信入口围栏、只读研究租约，三道门在读任何策略之前拒绝。
2. `policy.py`：权限引擎给首个判定；PTC 代理调用再叠加其参数的路径策略；只读 MCP 工具快速放行。
3. `allowlist.py`：ASK 命中 allowlist 条目、或命中可信工作区声明的命令前缀（仅限调用启动的那条单条命令）才放行；批量双保险、资金、不可逆社交、受保护指令文件（`is_protected_instruction_write` 读码判定）、其余只能由人答复的写入（`is_human_only` 读码判定，如 Git 钩子与配置）五道门对两类命中一视同仁、不可越过；组织策略忽略 allowlist 时两类命中一并忽略。
4. `allow_gates.py`：任何来源的 ALLOW，遇不可逆社交、资金、不可逆破坏性 shell，或 auto-mode 拒绝阈值被突破，退回 ASK。
5. ALLOW 的落定：`taint.py`（会话污点与工具 sink 冲突则转人工或交安全复核）；无污点时 `allow_review.py`（auto-mode 的外部代理出站复核与 shell 升级复核，通过后放行）。
6. `hitl.py`：DENY 拒绝；定时运行的 ASK 由作业声明裁决；浏览器域名已在本会话批准则放行；auto-mode 安全复核（资金、社交不可逆与只能由人答复的写入不交复核）；拒绝阈值被突破时 auto-mode 暂停并标高风险。
7. `pending.py`：仍挂起的调用补齐审批卡上下文与恢复时复核所需的摘要。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `evaluate_calls` | ✅ |
| `loop.py` | 核心 | `evaluate_calls`：组装批上下文，逐调用按阶段顺序判定 | ✅ |
| `state.py` | 核心 | `BatchContext`（一批内不变的判定依据）、`CallState`（单个调用的判定与审批卡上下文）、`Verdicts`（三个结果列表与落定方式） | ✅ |
| `preflight.py` | 核心 | 读策略之前的三道拒绝门 | ✅ |
| `policy.py` | 核心 | 引擎首个判定、PTC 路径策略、只读 MCP 快速放行 | ✅ |
| `allowlist.py` | 核心 | allowlist 条目与可信工作区声明前缀的命中、不可越过的五道门、组织策略忽略 allowlist | ✅ |
| `allow_gates.py` | 核心 | ALLOW 的统一复核：社交不可逆、资金、破坏性 shell、auto-mode 暂停 | ✅ |
| `taint.py` | 核心 | 污点 sink 冲突检测；冲突的 ALLOW 退回 ASK，auto-mode 下可由安全复核落定 | ✅ |
| `allow_review.py` | 核心 | 无污点 ALLOW 的 auto-mode 出站复核与 shell 升级复核，通过后放行 | ✅ |
| `hitl.py` | 核心 | DENY 拒绝、定时运行的 ASK 裁决、会话域名放行、auto-mode 安全复核（资金、社交不可逆与只能由人答复的写入除外）与暂停标记 | ✅ |
| `pending.py` | 核心 | 挂起调用的审批卡上下文：风险、批量影响、恢复提示、资金与不可逆标记、只能由人答复的写入隐藏「始终允许」（受保护指令文件按引擎的码认；引擎认不出的工具才看它在文件参数里点名的受保护文件）、回滚快照、脚本内容摘要 | ✅ |

## 依赖关系

- `loop.py` → 其余全部阶段模块与 `state.py`
- 各阶段模块 → `state.py`
- `preflight.py` → `../yolo.py`
- `allow_gates.py`、`pending.py` → `../_workspace_snapshot.py`
- `policy.py`、`allowlist.py`、`allow_review.py`、`hitl.py`、`pending.py` → `agent/security/command_rules.py`：命令文本只经它读取，读的是工具真正执行的那个参数
- `allowlist.py` → `agent/security/workspace_trust/`：信任级别、声明的前缀与前缀匹配谓词
- `allowlist.py`、`pending.py`、`hitl.py` → `agent/security/approval_reason.py`：`is_human_only`、`is_protected_instruction_write` 读引擎写下的码，判定哪些 ASK 只有人能答复、哪个是写指令文件
- `pending.py` → `../../_allow_always.py`：`protected_instruction_file_target` 与「始终允许」的拒绝闸门共用一处判定，卡片隐藏「始终允许」的条件与闸门拒绝记住的条件一致

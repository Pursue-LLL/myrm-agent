# skills/evolution_review/ 模块架构

## 架构概述

Evolution 审核子域。以 `ApprovalRecord` 为唯一事实源，提供类型（DTO/枚举/常量）、持久化、只读查询、写操作与落盘编排。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | 审核域类型：`EvolutionReviewRecord` / `EvolutionApprovalPayload`（含 `security_scan_summary`、提案所基于 SKILL.md 的 `base_content_hash`） / `RuntimeFailureEvidence` / 状态枚举 / `EVOLUTION_ACTION_TYPE` / `MAX_SKILL_CONTENT_CHARS` 常量 / 落盘失败原因码 `REASON_*`（`apply_failed` / `stale_base` / `skill_md_unloadable`）与携带原因码的 `EvolutionApplyError` / `ApprovalRecord` 转换 | ✅ |
| `persistence.py` | 核心 | ApprovalRecord 持久化读写（list/count 下推 SQL LIMIT + pending growth_status 过滤） | ✅ |
| `decision_lock.py` | 核心 | 同一条提案的决议函数同一时刻只运行一个（按第一个位置参数 `evolution_id` 的进程内锁，锁在持有者与等待者都离开后回收）：批准、拒绝、修订、回滚都是「读记录 → 落盘或改写 → 整条无条件写回」，交错执行时后写入者会盖掉先写入者的结果；成立的前提是服务端单进程 | ✅ |
| `queries.py` | 核心 | 创建（同时按磁盘上的 SKILL.md 记录 `base_content_hash`，文件不存在则为空）与只读查询（list/count 委托 persistence SQL） | ✅ |
| `actions.py` | 核心 | 审批 / 拒绝 / 修订 / 回滚；拒绝按审批状态分流：待审批的走审批注册表，已拒绝的重复拒绝与「已批准但从未落地」（手动批准后应用失败，状态保持 APPROVED，含失败后又修订过的）直接改写为已拒绝，已落地或已回滚的拒绝为冲突（409）；四个写操作都经 `decision_lock` 按提案串行，后到的读到先到的最终结果 | ✅ |
| `disk.py` | 核心 | 落盘编排（content / approval 成功路径）；失败时把 `EvolutionApplyError.code` 写成记录的 `reason_code`，其余异常记为 `apply_failed`；失败的 apply 不改动提案本身 | ✅ |
| `disk_content.py` | 核心 | 全量内容 apply（含 Copy-on-Write fork 及其 Agent 绑定改写）+ rollback（fork/衍生技能删除文件与记录、编辑类还原原内容；不改动 Agent 绑定）；写盘之前先校验：不支持的进化类型、提案创建之后 SKILL.md 已被改动或删除（磁盘哈希既不等于 `base_content_hash`，也不等于将要写入的内容；没有 `base_content_hash` 的提案不校验，fork 校验的是被 fork 的原技能文件；校验与写盘之间没有 `await`）、技能加载器无法加载的 SKILL.md（frontmatter 缺失/非法、无有效 description）一律以带原因码的 `EvolutionApplyError` 拒绝；写盘用 harness `infra.atomic_write`，写盘后记录或快照失败时按字节还原原文件（新建则删除文件及空目录）并重新抛出原异常，已写入的技能库记录不做补偿（`save_skill` 为 `INSERT OR REPLACE`，重试 apply 时被覆盖）；Copy-on-Write fork 的新身份（`skill_id` / `skill_name` / `skill_path`）仅在 apply 成功后才写回 payload；apply 后进化存储里保存的是实际写入磁盘的文本（含注入的 `scope_agent_id`）；`skill_file_differs` 比较磁盘上的 SKILL.md 与给定文本（换行写法不计，读不到的文件不算不同；读取与引擎共用 harness 的 `read_skill_md`，哈希基线与这里的比较因此读到同一份文本） | ✅ |

## 设计原则

- **事实源**：所有审核状态以 `ApprovalRecord` 行为事实源，`evolution_review` 只做投影与操作，不另设状态表。
- **依赖方向**：types ← persistence、disk_content ← queries、disk、decision_lock ← actions 单向依赖；跨子域引用根模块 `experience_ledger`（账本）时使用 `..experience_ledger` 相对导入。
- **IMPORT CONSTRAINT**：本包不做聚合导出（条件性依赖环见 `__init__.py`），外部一律穿透导入子模块；公共 API 由门面 `../evolution_reviews.py` 统一 re-export。

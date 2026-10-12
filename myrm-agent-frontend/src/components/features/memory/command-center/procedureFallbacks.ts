/**
 * [INPUT]
 * @/services/memory/procedureExperience::ProcedureMemoryEntryDTO
 *
 * [OUTPUT]
 * FALLBACK_PROCEDURES: Default simulated 8-field procedure memories for offline/test environments.
 *
 * [POS]
 * Fallback fixture for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 120 lines.
 */

import type { ProcedureMemoryEntryDTO } from '@/services/memory/procedureExperience';

export const FALLBACK_PROCEDURES: ProcedureMemoryEntryDTO[] = [
  {
    entry_id: 'proc_deploy_ci_01',
    name: '生产发布门禁流水线规范',
    retrieval_anchor: 'intent:deploy-ci-pipeline|pre:lint-clean,vitest-pass|app:production,release',
    operation_intent: '在将代码发布或合并至主分支前，执行严格的代码质量与无障碍门禁检查',
    preconditions: [
      '工作区无未暂存的致命破坏性代码变更',
      'Python 单测与前端 Vitest 单测均已全量运行',
    ],
    immutable_boundary: [
      '禁止直接使用 git push -f 覆盖主分支',
      '禁止为了省事而跳过 a11y ratchet 门禁',
    ],
    procedure_steps: [
      '1. 执行 bun run lint 并确保 0 errors',
      '2. 执行 bun scripts/check-a11y-ratchet.mjs 校验 0 违规',
      '3. 执行 pytest 验证框架与服务层全部回归通过',
      '4. 确认代码单文件行数严格控制在 400 行以内',
    ],
    write_field_provenance: {
      gate_status: '从 vitest 和 ruff 输出解析出的最终退出状态码',
      coverage_metrics: '单测汇总的 pass/fail 条数统计',
    },
    anti_patterns: [
      '绝不使用 any 类型注解，必须声明严格的具体类型',
      '绝不在修复 lint 时静默删除已有功能逻辑',
    ],
    applicability: [
      '代码提交前的 pre-commit 审查',
      '向远程生产环境部署应用时的自动化工作流',
    ],
    negative_applicability: [
      '临时本地调试原型开发且不打算提交的单机沙盒阶段',
    ],
    confidence: 1.0,
    created_at: new Date().toISOString(),
  },
  {
    entry_id: 'proc_data_isolation_02',
    name: '写前租户隔离与防越权校验',
    retrieval_anchor: 'intent:write-isolation-check|pre:session-scope-valid|app:database,mutation',
    operation_intent: '在执行持久化数据写操作前，强制执行作用域范围与租户隔离物理边界校验',
    preconditions: [
      '拥有明确的当前会话 session_id 或工作区作用域',
      '已获取待写入实体或记忆的归属上下文',
    ],
    immutable_boundary: [
      '禁止跨作用域污染全局未授权资产',
      '严格保证单机沙盒内部存储不发生跨用户泄露',
    ],
    procedure_steps: [
      '1. 提取当前调用上下文的 scope 与 session 标识',
      '2. 校验写入目标数据表对应的 WHERE 条件已绑定专属作用域',
      '3. 执行写入并记录操作审计指纹',
    ],
    write_field_provenance: {
      audit_fingerprint: '由时间戳与操作数据 SHA256 摘要派生',
    },
    anti_patterns: [
      '在没有 scope 过滤条件的情况下执行盲目批量更新',
    ],
    applicability: [
      '所有涉及数据库 INSERT/UPDATE/DELETE 的写操作前',
    ],
    negative_applicability: [
      '纯内存态临时只读计算，无任何磁盘持久化改动的场景',
    ],
    confidence: 1.0,
    created_at: new Date().toISOString(),
  },
];

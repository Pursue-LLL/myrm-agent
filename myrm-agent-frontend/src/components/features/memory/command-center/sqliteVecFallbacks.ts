/**
 * [INPUT]
 * @/services/memory::(SqliteVec DTOs)
 *
 * [OUTPUT]
 * Constants: FALLBACK_SQLITE_VEC_STATS, FALLBACK_SQLITE_VEC_SEARCH_RESPONSE,
 *            SAMPLE_QUERY_VECTORS
 *
 * [POS]
 * High-fidelity fallbacks for Item 130 SqliteVec Embedded Vector Store Suite.
 * Guarantees resilient WebUI preview and uninterrupted offline experience.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import type {
  SqliteVecSearchResponse,
  SqliteVecStatsResponse,
} from '@/services/memory';

export const FALLBACK_SQLITE_VEC_STATS: SqliteVecStatsResponse = {
  engine_mode: 'native_vec0',
  is_persistent: true,
  db_path: '~/.gemini/antigravity-cli/brain/memory_vault_vectors.sqlite',
  file_size_bytes: 4194304, // 4.0 MB
  collection_count: 3,
  total_documents: 1250,
  status: 'healthy',
};

export const SAMPLE_QUERY_VECTORS: { label: string; vector: number[] }[] = [
  {
    label: '系统技术规范与架构约束 (System Arch)',
    vector: [0.12, 0.45, -0.33, 0.88, 0.05, -0.19, 0.62, 0.41],
  },
  {
    label: '用户日常偏好与交互风格 (User Preference)',
    vector: [0.55, -0.21, 0.73, 0.14, -0.42, 0.31, -0.08, 0.67],
  },
  {
    label: '临时任务执行黑匣子日志 (Task Trace)',
    vector: [-0.34, 0.11, 0.09, -0.52, 0.81, -0.27, 0.39, -0.15],
  },
];

export const FALLBACK_SQLITE_VEC_SEARCH_RESPONSE: SqliteVecSearchResponse = {
  collection: 'agent_memory',
  total_returned: 3,
  apply_decay: true,
  execution_mode: 'native_vec0',
  results: [
    {
      id: 'doc_arch_001',
      content: '项目全局代码质量红线：单文件严格不超过400行，严禁使用any类型，所有Python/TS均具备强类型约束。',
      score: 0.94,
      raw_similarity: 0.96,
      decay_factor: 0.98,
      metadata: {
        category: 'architecture_standard',
        tier: 'P0',
        author: 'Lead Architect',
        timestamp: '2026-10-08T10:00:00Z',
      },
    },
    {
      id: 'doc_pref_002',
      content: '用户更倾向于使用精简自包含的 SQLite 单文件存储，拒绝在桌面环境运行沉重的 Docker 容器。',
      score: 0.87,
      raw_similarity: 0.91,
      decay_factor: 0.96,
      metadata: {
        category: 'user_preference',
        tier: 'P1',
        source: 'conversation_feedback',
        timestamp: '2026-10-07T18:30:00Z',
      },
    },
    {
      id: 'doc_hist_003',
      content: '历史部署记录：在离线低配沙箱中使用纯进程内存 Float32 BLOB 算法实现回退，计算指标符合验收标准。',
      score: 0.71,
      raw_similarity: 0.89,
      decay_factor: 0.80,
      metadata: {
        category: 'historical_trace',
        tier: 'P2',
        status: 'archived',
        timestamp: '2026-09-20T12:00:00Z',
      },
    },
  ],
};

/**
 * Multi-platform memory migration and import wizard fallback data.
 * Supplies graceful mock telemetry when offline or server endpoints are unavailable.
 */

import {
  DetectedCandidateDTO,
  ExtractedMemoryUnitDTO,
  MigrationImportResponseDTO,
  MigrationPreviewResponseDTO,
  MigrationRunReportDTO,
  MigrationSourceType,
} from '@/services/memory/memoryMigration';

export const mockSupportedSources: MigrationSourceType[] = [
  'openclaw',
  'hermes',
  'chatgpt_export',
  'claude_project',
  'memos',
  'markdown_tree',
  'generic_json',
];

export const mockDetectedCandidates: DetectedCandidateDTO[] = [
  {
    source_type: 'openclaw',
    artifact_path: '~/.openclaw/memory.json',
    estimated_entries: 14,
    summary: 'OpenClaw 原生记忆与用户画像归档 (JSON 格式)',
  },
  {
    source_type: 'hermes',
    artifact_path: '~/.hermes/memories/USER.md',
    estimated_entries: 28,
    summary: 'Hermes 认知规范与用户偏好 Markdown 记录',
  },
  {
    source_type: 'memos',
    artifact_path: '~/.memos/knowledge_graph.json',
    estimated_entries: 42,
    summary: 'MemOS 知识图谱实体与概念关联三元组',
  },
  {
    source_type: 'chatgpt_export',
    artifact_path: '~/Downloads/conversations.json',
    estimated_entries: 120,
    summary: 'ChatGPT 历史对话导出与自定义指示档案',
  },
];

export const mockPreviewUnits: ExtractedMemoryUnitDTO[] = [
  {
    source_type: 'openclaw',
    source_id: 'claw_fact_01',
    normalized_text: '用户偏好使用 TypeScript 和 Python，注重代码整洁度与高可维护性',
    layer: 'profile',
    tags: ['user_preference', 'tech_stack'],
    content_hash: '9a7c3b2f1e0d48a5',
  },
  {
    source_type: 'hermes',
    source_id: 'USER.md#L12',
    normalized_text: '严禁使用 Any 类型标注，严格执行社区 TypeScript PEP8 规范',
    layer: 'procedural',
    tags: ['coding_rule', 'guideline'],
    content_hash: '4f2e1a8b9c7d03e6',
  },
  {
    source_type: 'memos',
    source_id: 'memos_rel_03',
    normalized_text: 'UserPersona masters HybridSearchArchitecture',
    layer: 'semantic',
    tags: ['memos_relation', 'masters'],
    content_hash: '8b1d6c4e2a9f7051',
  },
];

export const mockImportReport: MigrationRunReportDTO = {
  migration_id: 'mig-demo-773a9',
  source_type: 'openclaw',
  source_path: '~/.openclaw/memory.json',
  total_scanned: 14,
  total_admitted: 12,
  total_skipped_duplicates: 2,
  total_chunks_generated: 16,
  vector_ingestion_status: 'success',
  latency_ms: 18.4,
  timestamp: Date.now() / 1000,
};

export const mockImportResponse: MigrationImportResponseDTO = {
  success: true,
  report: mockImportReport,
};

export const mockPreviewResponse: MigrationPreviewResponseDTO = {
  total_extracted: mockPreviewUnits.length,
  units: mockPreviewUnits,
};

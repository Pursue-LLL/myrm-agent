/**
 * [INPUT] next-intl::useTranslations (POS: 翻译函数类型)
 * [OUTPUT] DoctorExecutableAction / DoctorAction: 面板可派发的医生动作；MemoryTranslation 与就绪度、检查项、修复动作的取值守卫；formatTime / formatDuration / formatPercent: 展示格式化
 * [POS] Memory Doctor 面板各模块共用的类型、取值表与格式化函数，不含 React 渲染。
 */

import type { useTranslations } from 'next-intl';

export type MemoryTranslation = ReturnType<typeof useTranslations<'memory'>>;

const READINESS_STATUSES = ['ready', 'warning', 'critical', 'missing'] as const;
const DOCTOR_CHECK_IDS = [
  'relational_store',
  'memory_base_path',
  'context_bundle_manifest',
  'vector_index',
  'knowledge_graph',
  'embedding_provider',
  'event_ledger',
  'health_snapshot',
  'deployment_boundary',
  'embedding_live',
  'retrieval_pipeline',
  'sparse_cjk_recall',
  'golden_recall_benchmark',
  'memory_quality_governance',
  'memory_mislayer_governance',
  'migration_integrity',
  'capacity_theater',
] as const;
const DOCTOR_REPAIR_ACTIONS = [
  'review_storage_config',
  'enable_vector_store',
  'configure_embedding',
  'run_diagnostics',
  'run_health_refresh',
  'review_retrieval_trace',
  'restore_disciplined_defaults',
  'elevate_mislayered_memories',
] as const;

type ReadinessStatus = (typeof READINESS_STATUSES)[number];
type DoctorCheckId = (typeof DOCTOR_CHECK_IDS)[number];
type DoctorRepairAction = (typeof DOCTOR_REPAIR_ACTIONS)[number];
export type DoctorExecutableAction = Extract<
  DoctorRepairAction,
  'run_diagnostics' | 'run_health_refresh' | 'restore_disciplined_defaults' | 'elevate_mislayered_memories'
>;
/** The command center owns the doctor action union; the panel must accept every variant it dispatches. */
export type DoctorAction = DoctorExecutableAction;

export const isReadinessStatus = (value: string): value is ReadinessStatus =>
  READINESS_STATUSES.includes(value as ReadinessStatus);
export const isDoctorCheckId = (value: string): value is DoctorCheckId =>
  DOCTOR_CHECK_IDS.includes(value as DoctorCheckId);
export const isDoctorRepairAction = (value: string): value is DoctorRepairAction =>
  DOCTOR_REPAIR_ACTIONS.includes(value as DoctorRepairAction);
export const isExecutableDoctorAction = (value: string): value is DoctorExecutableAction =>
  value === 'run_diagnostics' ||
  value === 'run_health_refresh' ||
  value === 'restore_disciplined_defaults' ||
  value === 'elevate_mislayered_memories';

export const formatTime = (value?: string | null): string =>
  value
    ? new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(value))
    : '';

export const formatDuration = (value?: number | null): string => (value ? `${Math.round(value)}ms` : '-');
export const formatPercent = (value: number): string => `${Math.round(value * 100)}%`;

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandTimelineEvent (POS: Frontend Personal Brain Command Center client)
 *
 * [OUTPUT]
 * MEMORY_TYPES / MemoryTranslation: 记忆类型清单与 memory 命名空间翻译函数类型。
 * translateMemoryType / translateSpaceKind / translateRecordStatus / translateRuntimeStatus / translateTimelineTitle / translateOperationKind: 枚举值翻译，未知值原样回显。
 * formatTime / formatLiveStreamDescription: 时间与实时流事件描述格式化。
 * isCoverageStatus: 迁移覆盖状态守卫。
 *
 * [POS]
 * 个人大脑指挥中心面板共用的枚举守卫与文案格式化：未知枚举值原样回显，已知值走 memory 命名空间翻译。
 */

import type { useTranslations } from 'next-intl';
import type { MemoryCommandTimelineEvent } from '@/services/memory/commandCenter';
import type { MemoryType } from '@/services/memory';

export const MEMORY_TYPES: MemoryType[] = [
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
];
const SPACE_KINDS = ['global', 'agent', 'channel', 'conversation', 'task', 'shared', 'unknown'] as const;
const RECORD_STATUSES = ['pending', 'approved', 'rejected', 'active', 'archived', 'success'] as const;
const RUNTIME_STATUSES = [
  'available',
  'unavailable',
  'custom',
  'not_used',
  'proxied_by_sandbox',
  'persistent',
  'memory_fallback',
  'semantic',
  'keyword',
] as const;
const COVERAGE_STATUSES = ['not_tracked', 'partial', 'complete'] as const;

export type MemoryTranslation = ReturnType<typeof useTranslations<'memory'>>;
type SpaceKind = (typeof SPACE_KINDS)[number];
type RecordStatus = (typeof RECORD_STATUSES)[number];
type RuntimeStatus = (typeof RUNTIME_STATUSES)[number];
type CoverageStatus = (typeof COVERAGE_STATUSES)[number];

export const formatTime = (value: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

const isMemoryType = (value: string): value is MemoryType => MEMORY_TYPES.includes(value as MemoryType);
const isSpaceKind = (value: string): value is SpaceKind => SPACE_KINDS.includes(value as SpaceKind);
const isRecordStatus = (value: string): value is RecordStatus => RECORD_STATUSES.includes(value as RecordStatus);
const isRuntimeStatus = (value: string): value is RuntimeStatus => RUNTIME_STATUSES.includes(value as RuntimeStatus);
export const isCoverageStatus = (value: string): value is CoverageStatus =>
  COVERAGE_STATUSES.includes(value as CoverageStatus);

export const translateMemoryType = (value: string, t: MemoryTranslation): string =>
  isMemoryType(value) ? t(`types.${value}`) : value;
export const translateSpaceKind = (value: string, t: MemoryTranslation): string =>
  isSpaceKind(value) ? t(`commandCenter.spaceKind.${value}`) : value;
export const translateRecordStatus = (value: string, t: MemoryTranslation): string =>
  isRecordStatus(value) ? t(`commandCenter.recordStatus.${value}`) : value;
export const translateRuntimeStatus = (value: string, t: MemoryTranslation): string =>
  isRuntimeStatus(value) ? t(`commandCenter.runtimeStatus.${value}`) : value;
export const translateTimelineTitle = (event: MemoryCommandTimelineEvent, t: MemoryTranslation): string => {
  if (event.title === 'memory_health') {
    return t('commandCenter.healthCheck');
  }
  return translateMemoryType(event.title, t);
};

const WATERFALL_PHASES = [
  'observe',
  'scan',
  'propose',
  'approve',
  'write',
  'index',
  'recall',
  'inject',
  'cite',
  'verify',
] as const;

const OPERATION_KINDS = [
  ...WATERFALL_PHASES,
  'reject',
  'forget',
  'correct',
  'conflict',
  'maintenance',
  'import_memory',
  'export_memory',
  'health_check',
  'shared_context_proposal',
] as const;

export const translateOperationKind = (
  kind: string,
  t: MemoryTranslation,
  event?: MemoryCommandTimelineEvent,
): string => {
  if (kind === 'inject' && event?.metadata?.trigger === 'pre_compact') {
    return t('commandCenter.operationKind.pre_compact');
  }
  if (kind === 'write' && event?.metadata?.trigger === 'archive_checkpoint') {
    return t('commandCenter.operationKind.archive_checkpoint');
  }
  if ((OPERATION_KINDS as readonly string[]).includes(kind)) {
    return t(
      `commandCenter.operationKind.${kind}` as `commandCenter.operationKind.${(typeof OPERATION_KINDS)[number]}`,
    );
  }
  return kind.replaceAll('_', ' ');
};

export const formatLiveStreamDescription = (event: MemoryCommandTimelineEvent, t: MemoryTranslation): string => {
  if (event.kind === 'inject' && event.metadata?.trigger === 'pre_compact') {
    return t('commandCenter.preCompactLiveDescription', {
      count: String((event.metadata.recalled_ids as string | undefined)?.split(',').filter(Boolean).length ?? 0),
    });
  }
  if (event.kind === 'write' && event.metadata?.trigger === 'archive_checkpoint') {
    return t('commandCenter.archiveCheckpointLiveDescription', {
      tool: String(event.metadata.tool_name ?? 'tool'),
      path: String(event.metadata.archive_path ?? ''),
    });
  }
  const stepCount = event.metadata?.live_stream_step_count;
  if (event.kind === 'recall' && typeof stepCount === 'number' && stepCount > 1) {
    return t('commandCenter.recallBurstSummary', { count: stepCount, summary: event.description });
  }
  return event.description;
};

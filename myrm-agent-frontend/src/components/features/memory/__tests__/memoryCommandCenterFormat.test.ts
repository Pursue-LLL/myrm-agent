/**
 * [INPUT]
 * ../command-center/memoryCommandCenterFormat::translate* (POS: 个人大脑指挥中心面板共用的枚举守卫与文案格式化)
 *
 * [OUTPUT]
 * memoryCommandCenterFormat tests: 枚举翻译命中与回显、操作类型与实时流描述的分支、枚举守卫。
 *
 * [POS]
 * 命令中心文案格式化回归测试。验证已知枚举走翻译键、未知枚举原样回显，以及压缩前注入、归档检查点、召回合并三类特殊描述。
 */
import { describe, expect, it } from 'vitest';

import type { MemoryCommandTimelineEvent } from '@/services/memory/commandCenter';
import {
  formatLiveStreamDescription,
  formatTime,
  isCoverageStatus,
  isMigrationAdapterStatus,
  translateMemoryType,
  translateOperationKind,
  translateRecordStatus,
  translateRuntimeStatus,
  translateSpaceKind,
  translateTimelineTitle,
  type MemoryTranslation,
} from '../command-center/memoryCommandCenterFormat';

const t = ((key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${JSON.stringify(values)}` : key) as unknown as MemoryTranslation;

const makeEvent = (overrides: Partial<MemoryCommandTimelineEvent>): MemoryCommandTimelineEvent =>
  ({
    id: 'evt-1',
    kind: 'recall',
    title: 'semantic',
    description: 'raw description',
    occurred_at: '2026-04-29T08:05:00Z',
    metadata: {},
    ...overrides,
  }) as unknown as MemoryCommandTimelineEvent;

describe('enum translators', () => {
  it('translate known values through their translation keys', () => {
    expect(translateMemoryType('semantic', t)).toBe('types.semantic');
    expect(translateSpaceKind('shared', t)).toBe('commandCenter.spaceKind.shared');
    expect(translateRecordStatus('approved', t)).toBe('commandCenter.recordStatus.approved');
    expect(translateRuntimeStatus('memory_fallback', t)).toBe('commandCenter.runtimeStatus.memory_fallback');
  });

  it('echo unknown values instead of a missing translation key', () => {
    expect(translateMemoryType('brand_new_type', t)).toBe('brand_new_type');
    expect(translateSpaceKind('galaxy', t)).toBe('galaxy');
    expect(translateRecordStatus('limbo', t)).toBe('limbo');
    expect(translateRuntimeStatus('exploding', t)).toBe('exploding');
  });

  it('resolve the timeline title: health snapshots get their own label, the rest are memory types', () => {
    expect(translateTimelineTitle(makeEvent({ title: 'memory_health' }), t)).toBe('commandCenter.healthCheck');
    expect(translateTimelineTitle(makeEvent({ title: 'episodic' }), t)).toBe('types.episodic');
    expect(translateTimelineTitle(makeEvent({ title: 'custom title' }), t)).toBe('custom title');
  });
});

describe('translateOperationKind', () => {
  it('translates known operation kinds', () => {
    expect(translateOperationKind('recall', t)).toBe('commandCenter.operationKind.recall');
    expect(translateOperationKind('import_memory', t)).toBe('commandCenter.operationKind.import_memory');
  });

  it('distinguishes pre-compact injection and archive-checkpoint writes by trigger', () => {
    expect(
      translateOperationKind('inject', t, makeEvent({ kind: 'inject', metadata: { trigger: 'pre_compact' } })),
    ).toBe('commandCenter.operationKind.pre_compact');
    expect(
      translateOperationKind('write', t, makeEvent({ kind: 'write', metadata: { trigger: 'archive_checkpoint' } })),
    ).toBe('commandCenter.operationKind.archive_checkpoint');
    expect(translateOperationKind('inject', t, makeEvent({ kind: 'inject' }))).toBe(
      'commandCenter.operationKind.inject',
    );
  });

  it('humanises unknown kinds', () => {
    expect(translateOperationKind('some_future_kind', t)).toBe('some future kind');
  });
});

describe('formatLiveStreamDescription', () => {
  it('counts the recalled ids of a pre-compact injection and ignores empty segments', () => {
    const event = makeEvent({ kind: 'inject', metadata: { trigger: 'pre_compact', recalled_ids: 'a,b,,c' } });
    expect(formatLiveStreamDescription(event, t)).toBe('commandCenter.preCompactLiveDescription:{"count":"3"}');
  });

  it('reports zero recalled ids when the metadata has none', () => {
    const event = makeEvent({ kind: 'inject', metadata: { trigger: 'pre_compact' } });
    expect(formatLiveStreamDescription(event, t)).toBe('commandCenter.preCompactLiveDescription:{"count":"0"}');
  });

  it('describes archive checkpoints with the tool and archive path', () => {
    const event = makeEvent({
      kind: 'write',
      metadata: { trigger: 'archive_checkpoint', tool_name: 'bash', archive_path: '/tmp/out.log' },
    });
    expect(formatLiveStreamDescription(event, t)).toBe(
      'commandCenter.archiveCheckpointLiveDescription:{"tool":"bash","path":"/tmp/out.log"}',
    );
  });

  it('summarises coalesced recall bursts only when more than one step was merged', () => {
    const burst = makeEvent({ kind: 'recall', metadata: { live_stream_step_count: 3 } });
    expect(formatLiveStreamDescription(burst, t)).toBe(
      'commandCenter.recallBurstSummary:{"count":3,"summary":"raw description"}',
    );
    const single = makeEvent({ kind: 'recall', metadata: { live_stream_step_count: 1 } });
    expect(formatLiveStreamDescription(single, t)).toBe('raw description');
  });

  it('falls back to the event description', () => {
    expect(formatLiveStreamDescription(makeEvent({ kind: 'write' }), t)).toBe('raw description');
  });
});

describe('guards and time formatting', () => {
  it('recognise only declared coverage and adapter statuses', () => {
    expect(isCoverageStatus('partial')).toBe(true);
    expect(isCoverageStatus('half')).toBe(false);
    expect(isMigrationAdapterStatus('missing')).toBe(true);
    expect(isMigrationAdapterStatus('unknown')).toBe(false);
  });

  it('formats an ISO timestamp into a short locale string', () => {
    const formatted = formatTime('2026-04-29T08:05:00Z');
    expect(formatted).not.toBe('Invalid Date');
    expect(formatted).toMatch(/\d/);
  });
});

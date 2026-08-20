/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../MemoryCommandCenterPanels::ActSection (POS: 个人大脑指挥中心基础展示面板，含 migration missing 动作闭环)
 *
 * [OUTPUT]
 * MemoryCommandCenterPanels migration actions tests: missing 状态按钮渲染与动作回调守卫。
 *
 * [POS]
 * 记忆中心 migration adapter UI 回归测试。验证 missing 状态动作闭环可触发，all-ready 场景无误触发入口。
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { MemoryCommandCenterResponse } from '@/services/memory/commandCenter';
import { ActSection, VerifySection } from '../command-center/MemoryCommandCenterPanels';
type ActSectionProps = Parameters<typeof ActSection>[0];
type VerifySectionProps = Parameters<typeof VerifySection>[0];

const makeSnapshot = (adapterStatus: Record<string, 'ready' | 'planned' | 'missing'>): MemoryCommandCenterResponse =>
  ({
    governance: [],
    migration: {
      supported_sources: Object.keys(adapterStatus),
      tracked_imports: 0,
      unmapped_items: 0,
      coverage_status: 'not_tracked',
      adapter_status: adapterStatus,
      last_import_batch_id: null,
      verification_recommended: false,
      cleanup_pending_sessions: 0,
      cleanup_confirmed_sessions: 0,
      cleanup_expired_sessions: 0,
      cleanup_rolled_back_sessions: 0,
      cleanup_retention_days: 30,
    },
  }) as unknown as MemoryCommandCenterResponse;

const t = ((key: string, values?: { source?: string }) => {
  if (typeof values?.source === 'string') {
    return `${key}:${values.source}`;
  }
  return key;
}) as ActSectionProps['t'];

describe('MemoryCommandCenterPanels migration actions', () => {
  it('shows actionable button for missing adapter status', async () => {
    const user = userEvent.setup();
    const onOpenMigrationWizard = vi.fn();

    render(
      <ActSection
        snapshot={makeSnapshot({ gbrain: 'missing', openclaw: 'ready' })}
        t={t}
        actionId={null}
        onAction={() => {}}
        onDoctorAction={() => {}}
        onRollbackImport={() => {}}
        onOpenMigrationWizard={onOpenMigrationWizard}
      />,
    );

    expect(screen.getByText('commandCenter.migrationAdapterMissingHint:gbrain')).toBeInTheDocument();
    const openButtons = screen.getAllByRole('button', { name: 'commandCenter.migrationAdapterOpenWizard' });
    expect(openButtons).toHaveLength(1);
    await user.click(openButtons[0]);
    expect(onOpenMigrationWizard).toHaveBeenCalledWith('gbrain');
  });

  it('does not render missing-action button when all adapters are ready', () => {
    render(
      <ActSection
        snapshot={makeSnapshot({ openclaw: 'ready', hermes: 'ready' })}
        t={t}
        actionId={null}
        onAction={() => {}}
        onDoctorAction={() => {}}
        onRollbackImport={() => {}}
        onOpenMigrationWizard={() => {}}
      />,
    );

    expect(screen.queryByRole('button', { name: 'commandCenter.migrationAdapterOpenWizard' })).toBeNull();
  });
});

const makeRuntimeSnapshot = (
  vectorPersistence: 'persistent' | 'memory_fallback' | 'unavailable',
): MemoryCommandCenterResponse =>
  ({
    generated_at: '2026-04-29T00:00:00Z',
    runtime: {
      deploy_mode: 'local',
      storage_mode: 'local_files',
      memory_base_path: '/tmp/myrm-memory',
      relational_status: 'available',
      vector_status: 'available',
      vector_persistence: vectorPersistence,
      graph_status: 'available',
      embedding_status: 'custom',
      control_plane_status: 'not_used',
      event_ledger_status: 'available',
      health_snapshot_status: 'available',
      supported_clients: ['local_web'],
    },
    cost: { prompt_tokens: 0, cached_tokens: 0, completion_tokens: 0, cache_friendly: false },
    replay: [],
    waterfall: [],
    replay_events: [],
    doctor_checks: [],
    trace_runs: [],
    eval_metrics: [],
    connectors: [],
    privacy: [],
    plane_summary: {
      event_count: 0,
      failed_event_count: 0,
      queue_backlog: 0,
      import_rollback_health_status: 'healthy',
      import_rollback_in_progress: 0,
      import_rollback_failed: 0,
      import_rollback_partial: 0,
      import_rollback_missing_items: 0,
      import_rollback_failed_items: 0,
      archive_restore_health_status: 'healthy',
      archive_restore_in_progress: 0,
      archive_restore_failed: 0,
      archive_restore_partial: 0,
      archive_restore_rollback_in_progress: 0,
      archive_restore_rollback_failed: 0,
      archive_restore_missing_items: 0,
      archive_restore_failed_items: 0,
      last_event_at: null,
    },
  }) as unknown as MemoryCommandCenterResponse;

const renderVerify = (snapshot: MemoryCommandCenterResponse) => {
  const verifyProps = {
    snapshot,
    t,
    actionId: null,
    diagnosticRun: null,
    diagnosticHistory: [],
    onDoctorAction: () => {},
  } as unknown as VerifySectionProps;
  render(<VerifySection {...verifyProps} />);
};

describe('MemoryCommandCenterPanels vector persistence', () => {
  it('highlights memory_fallback with alert styling and translated value', () => {
    renderVerify(makeRuntimeSnapshot('memory_fallback'));

    const label = screen.getByText('commandCenter.vectorPersistence');
    const row = label.closest('div');
    expect(row?.className).toContain('border-amber-500/50');
    expect(screen.getByText('commandCenter.runtimeStatus.memory_fallback')).toBeInTheDocument();
  });

  it('shows persistent without alert styling', () => {
    renderVerify(makeRuntimeSnapshot('persistent'));

    const label = screen.getByText('commandCenter.vectorPersistence');
    const row = label.closest('div');
    expect(row?.className).not.toContain('border-amber-500/50');
    expect(screen.getByText('commandCenter.runtimeStatus.persistent')).toBeInTheDocument();
  });

  it('renders unavailable persistence state without alert styling', () => {
    renderVerify(makeRuntimeSnapshot('unavailable'));

    const label = screen.getByText('commandCenter.vectorPersistence');
    const row = label.closest('div');
    expect(row?.className).not.toContain('border-amber-500/50');
    expect(screen.getByText('commandCenter.runtimeStatus.unavailable')).toBeInTheDocument();
  });
});

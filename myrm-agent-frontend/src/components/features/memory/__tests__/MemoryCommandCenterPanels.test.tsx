/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../command-center/MemoryCommandCenterPanels::ActSection (POS: 个人大脑指挥中心基础展示面板)
 *
 * [OUTPUT]
 * MemoryCommandCenterPanels migration entry tests: manifest 驱动的导入入口渲染与动作回调守卫。
 *
 * [POS]
 * 记忆中心迁移面板 UI 回归测试。验证导入入口常显、manifest chips 深链到对应导入源，覆盖状态与计数如实展示。
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type {
  MemoryCommandCenterResponse,
  MemoryCommandMigrationProvenance,
  MemoryCommandMigrationSourceManifestItem,
} from '@/services/memory/commandCenter';
import { ActSection, VerifySection } from '../command-center/MemoryCommandCenterPanels';
type ActSectionProps = Parameters<typeof ActSection>[0];
type VerifySectionProps = Parameters<typeof VerifySection>[0];

const MANIFEST: MemoryCommandMigrationSourceManifestItem[] = [
  {
    id: 'claude-code',
    display_name: 'Claude Code',
    import_source: 'claude_code_jsonl',
    discover_modes: ['local_scan', 'zip_upload'],
    deep_link_enabled: true,
  },
  {
    id: 'openclaw',
    display_name: 'OpenClaw',
    import_source: 'openclaw',
    discover_modes: ['local_scan'],
    deep_link_enabled: false,
  },
];

const makeSnapshot = (migration: Partial<MemoryCommandMigrationProvenance> = {}): MemoryCommandCenterResponse =>
  ({
    governance: [],
    migration: {
      tracked_imports: 0,
      unmapped_items: 0,
      coverage_status: 'not_tracked',
      source_manifest: MANIFEST,
      last_import_batch_id: null,
      verification_recommended: false,
      cleanup_pending_sessions: 0,
      cleanup_confirmed_sessions: 0,
      cleanup_expired_sessions: 0,
      cleanup_rolled_back_sessions: 0,
      cleanup_retention_days: 30,
      ...migration,
    },
  }) as unknown as MemoryCommandCenterResponse;

const t = ((key: string, values?: { source?: string }) => {
  if (typeof values?.source === 'string') {
    return `${key}:${values.source}`;
  }
  return key;
}) as ActSectionProps['t'];

describe('MemoryCommandCenterPanels migration entry', () => {
  it('keeps the wizard entry visible and deep-links manifest chips to their source id', async () => {
    const user = userEvent.setup();
    const onOpenMigrationWizard = vi.fn();

    render(
      <ActSection
        snapshot={makeSnapshot()}
        t={t}
        actionId={null}
        onAction={() => {}}
        onDoctorAction={() => {}}
        onRollbackImport={() => {}}
        onOpenMigrationWizard={onOpenMigrationWizard}
      />,
    );

    expect(screen.getByText('commandCenter.coverageStatus.not_tracked')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.trackedImports')).toBeInTheDocument();

    const openButtons = screen.getAllByRole('button', { name: 'commandCenter.migrationOpenWizard' });
    expect(openButtons).toHaveLength(1);
    await user.click(openButtons[0]);
    expect(onOpenMigrationWizard).toHaveBeenCalledWith('');

    expect(screen.getByRole('button', { name: 'Claude Code' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'OpenClaw' }));
    expect(onOpenMigrationWizard).toHaveBeenLastCalledWith('openclaw');
  });

  it('renders the manifest chips that the server advertises', () => {
    render(
      <ActSection
        snapshot={makeSnapshot({
          source_manifest: [MANIFEST[1]],
          coverage_status: 'partial',
          tracked_imports: 3,
          unmapped_items: 2,
        })}
        t={t}
        actionId={null}
        onAction={() => {}}
        onDoctorAction={() => {}}
        onRollbackImport={() => {}}
        onOpenMigrationWizard={() => {}}
      />,
    );

    expect(screen.getByText('commandCenter.coverageStatus.partial')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'OpenClaw' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Claude Code' })).toBeNull();
  });
});

const makeRuntimeSnapshot = (
  vectorPersistence: 'persistent' | 'memory_fallback' | 'unavailable',
): MemoryCommandCenterResponse =>
  ({
    generated_at: '2026-04-29T00:00:00Z',
    runtime: {
      deploy_mode: 'local',
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

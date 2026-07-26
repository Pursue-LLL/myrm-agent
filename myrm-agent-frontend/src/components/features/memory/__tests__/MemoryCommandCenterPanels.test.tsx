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

import type { MemoryCommandCenterResponse } from '@/services/memoryCommandCenter';
import { ActSection } from '../MemoryCommandCenterPanels';
type ActSectionProps = Parameters<typeof ActSection>[0];

const makeSnapshot = (
  adapterStatus: Record<string, 'ready' | 'planned' | 'missing'>,
): MemoryCommandCenterResponse =>
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

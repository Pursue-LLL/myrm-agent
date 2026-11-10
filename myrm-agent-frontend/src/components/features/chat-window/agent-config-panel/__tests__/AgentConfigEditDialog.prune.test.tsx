/**
 * Pruning of stale core skills from the edit dialog.
 *
 * Real scenario: the skills card warns when a core skill of the draft went stale and offers to prune. The curator
 * sweep runs once at a time, tells the user what it found or that it failed, and refreshes the skill list.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CuratorRunResponse } from '@/services/skill';
import { deferred } from '@/test-utils/deferred';

import type { ConfigCardType } from '../AgentConfigCards';
import { dialogProps, kit, resetKit, skill, skillsPanel, type DialogProps } from './editDialogKit';
import { installFakeServer } from './editDialogRequests';

const { stableT } = vi.hoisted(() => ({
  stableT: Object.assign(
    (key: string, values?: Record<string, string | number>) => (values ? `${key}:${JSON.stringify(values)}` : key),
    { has: (key: string) => key.trim().length > 0 },
  ),
}));
vi.mock('next-intl', () => ({ useTranslations: () => stableT, useLocale: () => 'en' }));
vi.mock('next/dynamic', async () => (await import('./editDialogKit')).nextDynamicMock());
vi.mock('@/hooks/billing/useFeatureEntitlements', async () => (await import('./editDialogKit')).entitlementsMock());
vi.mock('@/lib/deploy-mode', async (importOriginal) =>
  (await import('./editDialogKit')).deployModeMock(await importOriginal<typeof import('@/lib/deploy-mode')>()),
);
vi.mock('@/hooks/shared/useToast', async () => ({ toast: (await import('./editDialogKit')).kit.toast }));
vi.mock('@/services/skill', async (importOriginal) => {
  const { kit: shared } = await import('./editDialogKit');
  return {
    ...(await importOriginal<typeof import('@/services/skill')>()),
    runCuratorSweep: () => shared.runCuratorSweep(),
  };
});
vi.mock('../ActionSpaceAccuracyRadar', async () => (await import('./editDialogKit')).radarMock());
vi.mock('../SkillsSectionPanel', async () => (await import('./editDialogKit')).skillsPanelMock());
vi.mock('../BuiltinToolsPanel', async () => (await import('./editDialogKit')).builtinToolsPanelMock());
vi.mock('../SubagentsPanel', async () => (await import('./editDialogKit')).subagentsPanelMock());
vi.mock('../InstructionPanel', async () => (await import('./editDialogKit')).instructionPanelMock());

import AgentConfigEditDialog from '../AgentConfigEditDialog';

const radar = () => screen.getByTestId('radar');

function show(type: ConfigCardType, overrides: Partial<DialogProps> = {}) {
  return render(<AgentConfigEditDialog {...dialogProps(type, overrides)} />);
}

beforeEach(() => {
  vi.resetAllMocks();
  resetKit();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  installFakeServer();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AgentConfigEditDialog: stale core skills and pruning', () => {
  const stale = {
    call_count: 0,
    success_count: 0,
    failure_count: 0,
    last_used_at: null,
    success_rate: 0,
    pinned: false,
  };
  const staleSkills = [
    skill('s1', { usage_stats: { ...stale, lifecycle_status: 'stale' } }),
    skill('s2', { usage_stats: { ...stale, lifecycle_status: 'stale' } }),
    skill('s3', { usage_stats: { ...stale, lifecycle_status: 'active' } }),
  ];
  const sweep: CuratorRunResponse = {
    skills_scanned: 9,
    total_transitions: 3,
    stale_count: 2,
    archived_count: 1,
    skipped_pinned: 0,
    skipped_protected: 0,
    transitions: [],
  };
  const prune = async () => {
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'prune' }));
    });
  };
  const toastTitles = () => kit.toast.mock.calls.map(([options]) => options.title);

  it('counts the selected core skills that went stale, and no others', () => {
    show('skills', {
      enabledSkills: staleSkills,
      selectedSkillIds: ['s1', 's2', 's3'],
      skillConfigs: { s1: { is_core: true }, s2: {}, s3: { is_core: true } },
    });

    expect(radar()).toHaveAttribute('data-stale', '1');
    expect(screen.getByTestId('skills-panel')).toHaveAttribute('data-stale', 's1');
  });

  it('prunes through the curator, refreshes the skills and reports the counts', async () => {
    const refresh = vi.fn(async () => undefined);
    kit.runCuratorSweep.mockResolvedValue(sweep);
    show('skills', { onRefreshSkills: refresh });

    await prune();

    expect(toastTitles()).toEqual([
      'actionSpaceRadar.smartPruneRunning',
      'actionSpaceRadar.smartPruneSuccess:{"stale":2,"archived":1}',
    ]);
    expect(refresh).toHaveBeenCalledOnce();
    expect(radar()).toHaveAttribute('data-pruning', 'false');
  });

  it('prunes when the skills panel asks for it as well', async () => {
    kit.runCuratorSweep.mockResolvedValue(sweep);
    show('skills');

    await act(async () => {
      skillsPanel().onSmartPrune();
    });

    expect(kit.runCuratorSweep).toHaveBeenCalledOnce();
  });

  it('prunes just as well when there is nothing to refresh', async () => {
    kit.runCuratorSweep.mockResolvedValue(sweep);
    show('skills');

    await prune();

    expect(toastTitles()).toEqual([
      'actionSpaceRadar.smartPruneRunning',
      'actionSpaceRadar.smartPruneSuccess:{"stale":2,"archived":1}',
    ]);
  });

  it('reports a failed prune and leaves the skills as they are', async () => {
    const refresh = vi.fn(async () => undefined);
    kit.runCuratorSweep.mockRejectedValue(new Error('curator down'));
    show('skills', { onRefreshSkills: refresh });

    await prune();

    expect(kit.toast).toHaveBeenLastCalledWith({ title: 'actionSpaceRadar.smartPruneFailed', variant: 'destructive' });
    expect(refresh).not.toHaveBeenCalled();
    expect(radar()).toHaveAttribute('data-pruning', 'false');
  });

  it('runs one prune at a time', async () => {
    const pending = deferred<CuratorRunResponse>();
    kit.runCuratorSweep.mockImplementation(() => pending.promise);
    show('skills');

    fireEvent.click(screen.getByRole('button', { name: 'prune' }));
    expect(radar()).toHaveAttribute('data-pruning', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'prune' }));
    expect(kit.runCuratorSweep).toHaveBeenCalledOnce();

    await act(async () => {
      pending.reject(new Error('stop'));
      await pending.promise.catch(() => undefined);
    });
    expect(radar()).toHaveAttribute('data-pruning', 'false');
  });
});

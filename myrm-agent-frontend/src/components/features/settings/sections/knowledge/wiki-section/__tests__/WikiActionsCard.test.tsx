/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit } from './wikiSectionTestKit';
import { stubProps } from './wikiSectionStubs';
import { compileRunOf, snapshotOf } from './wikiSectionFixtures';
import { WikiActionsCard } from '../WikiActionsCard';
import type { WikiMaintenanceController } from '../useWikiMaintenance';

type CardProps = Parameters<typeof WikiActionsCard>[0];

interface PhaseBarProps {
  compileRun: unknown;
  pendingCount: number;
  processingCount: number;
  forceVisible: boolean;
}

function renderCard(
  over: { maintenance?: Partial<WikiMaintenanceController>; overview?: Partial<CardProps['overview']> } = {},
) {
  const maintenance: WikiMaintenanceController = {
    maintainMode: 'structural',
    setMaintainMode: vi.fn(),
    isCompiling: false,
    isResumingCompile: false,
    isRepairingTypes: false,
    isRepairingPublication: false,
    isReindexingVectors: false,
    reindexErrors: [],
    isWikiCompileBusy: false,
    isMaintaining: false,
    maintainProgressLabel: null,
    canCancelMaintain: false,
    isCancellingMaintain: false,
    handleCompile: vi.fn(),
    handleResumeCompile: vi.fn(),
    handleMaintain: vi.fn(),
    handleCancelMaintain: vi.fn(),
    handleRepairPageTypes: vi.fn(),
    handleRepairPublication: vi.fn(),
    handleReindexVectors: vi.fn(),
    ...over.maintenance,
  };
  const overview: CardProps['overview'] = { compileRun: null, ingestSnapshot: null, ...over.overview };
  const onViewQueue = vi.fn();
  render(<WikiActionsCard maintenance={maintenance} overview={overview} onViewQueue={onViewQueue} />);
  return { maintenance, onViewQueue };
}

const button = (name: string) => screen.getByRole<HTMLButtonElement>('button', { name });
const phaseBar = () => stubProps<PhaseBarProps & Record<string, unknown>>('WikiCompilePhaseBar');
const shownMode = () => document.querySelector('[data-slot="select-value"]')?.textContent;

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiActionsCard: paused compile circuit', () => {
  const paused = compileRunOf({ state: 'paused', pause_reason: 'Provider quota exhausted' });

  it('explains why compiling stopped and offers to resume or look at the queue', async () => {
    const { maintenance, onViewQueue } = renderCard({ overview: { compileRun: paused } });
    expect(screen.getByText('compileRun.pausedTitle')).toBeTruthy();
    expect(screen.getByText('Provider quota exhausted')).toBeTruthy();
    await click(button('compileRun.resume'));
    expect(maintenance.handleResumeCompile).toHaveBeenCalledExactlyOnceWith();
    await click(button('compileRun.viewQueue'));
    expect(onViewQueue).toHaveBeenCalledOnce();
  });

  it('falls back to the default explanation when the server gave no reason', () => {
    renderCard({ overview: { compileRun: compileRunOf({ state: 'paused', pause_reason: '' }) } });
    expect(screen.getByText('compileRun.pausedDefault')).toBeTruthy();
  });

  it('locks the resume button while it resumes, and says so', () => {
    renderCard({ overview: { compileRun: paused }, maintenance: { isResumingCompile: true } });
    expect(button('compileRun.resuming').disabled).toBe(true);
    expect(screen.queryByRole('button', { name: 'compileRun.resume' })).toBeNull();
  });

  it('keeps the phase bar away and blocks a new compile while the circuit is paused', () => {
    renderCard({ overview: { compileRun: paused } });
    expect(screen.queryByTestId('WikiCompilePhaseBar')).toBeNull();
    expect(button('actions.compile').disabled).toBe(true);
  });

  it('shows no banner for a circuit that is running', () => {
    renderCard({ overview: { compileRun: compileRunOf({ state: 'running' }) } });
    expect(screen.queryByText('compileRun.pausedTitle')).toBeNull();
    expect(button('actions.compile').disabled).toBe(false);
  });
});

describe('WikiActionsCard: compile phase bar', () => {
  it('shows no phase bar without a compile run', () => {
    renderCard();
    expect(screen.queryByTestId('WikiCompilePhaseBar')).toBeNull();
  });

  it('follows the live queue, and stays visible while this page is compiling', () => {
    const run = compileRunOf({ state: 'running' });
    renderCard({
      overview: { compileRun: run, ingestSnapshot: snapshotOf({ pending: 4, processing: 2 }) },
      maintenance: { isCompiling: true },
    });
    expect(phaseBar()).toMatchObject({ compileRun: run, pendingCount: 4, processingCount: 2, forceVisible: true });
  });

  it('counts an empty queue as zero when there is no live snapshot', () => {
    renderCard({ overview: { compileRun: compileRunOf({ state: 'running' }) } });
    expect(phaseBar()).toMatchObject({ pendingCount: 0, processingCount: 0, forceVisible: false });
  });
});

describe('WikiActionsCard: maintenance mode', () => {
  it.each([
    ['structural', 'actions.maintainModeStructural'],
    ['full', 'actions.maintainModeFull'],
  ] as const)('shows the %s mode as %s, labelled for its picker', (mode, label) => {
    renderCard({ maintenance: { maintainMode: mode } });
    expect(document.querySelector('[data-slot="select"]')?.getAttribute('data-value')).toBe(mode);
    expect(shownMode()).toBe(label);
    expect(screen.getByText('actions.maintainModeLabel').getAttribute('for')).toBe('wiki-maintain-mode');
  });

  it('switches between structural and full maintenance', async () => {
    const { maintenance } = renderCard();
    await click(screen.getByRole('option', { name: 'actions.maintainModeFull' }));
    expect(maintenance.setMaintainMode).toHaveBeenLastCalledWith('full');
    await click(screen.getByRole('option', { name: 'actions.maintainModeStructural' }));
    expect(maintenance.setMaintainMode).toHaveBeenLastCalledWith('structural');
    expect(maintenance.setMaintainMode).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['structural', false, 'actions.maintainModeStructuralHint'],
    ['full', false, 'actions.maintainModeFullHint'],
    ['structural', true, 'actions.maintainCompileBusyHint'],
    ['full', true, 'actions.maintainCompileBusyHint'],
  ] as const)('in %s mode with compile busy = %s the hint says %s', (mode, busy, hint) => {
    renderCard({ maintenance: { maintainMode: mode, isWikiCompileBusy: busy } });
    expect(screen.getAllByText(/^actions\.maintain\w*Hint$/).map((node) => node.textContent)).toEqual([hint]);
  });
});

describe('WikiActionsCard: compile and maintain buttons', () => {
  it.each([
    [{}, 'actions.compile', false],
    [{ isWikiCompileBusy: true }, 'compiling', false],
    [{ isCompiling: true, isWikiCompileBusy: true }, 'compiling', true],
  ])('with %j the compile button says %s and is disabled = %s', (state, label, disabled) => {
    renderCard({ maintenance: state });
    expect(button(label).disabled).toBe(disabled);
  });

  it('starts a compile', async () => {
    const { maintenance } = renderCard();
    await click(button('actions.compile'));
    expect(maintenance.handleCompile).toHaveBeenCalledOnce();
  });

  it.each([
    ['idle', {}, 'actions.maintain', false],
    ['running without progress', { isMaintaining: true }, 'maintaining', true],
    [
      'running with progress',
      {
        isMaintaining: true,
        maintainProgressLabel: { key: 'maintainProgress.driftReview', values: { done: 1, total: 4 } },
      },
      'maintainProgress.driftReview|{"done":1,"total":4}',
      true,
    ],
    ['blocked by a compile', { isWikiCompileBusy: true }, 'actions.maintain', true],
  ] as const)('shows maintenance as %s', (_label, state, label, disabled) => {
    renderCard({ maintenance: state });
    const maintain = screen.getByTestId('wiki-maintain-button') as HTMLButtonElement;
    expect(maintain.textContent).toBe(label);
    expect(maintain.disabled).toBe(disabled);
  });

  it('starts maintenance', async () => {
    const { maintenance } = renderCard();
    await click(screen.getByTestId('wiki-maintain-button'));
    expect(maintenance.handleMaintain).toHaveBeenCalledOnce();
  });
});

describe('WikiActionsCard: stopping maintenance', () => {
  it.each([
    ['nothing is running', { isMaintaining: false, canCancelMaintain: true }],
    ['the run cannot be stopped', { isMaintaining: true, canCancelMaintain: false, isCancellingMaintain: false }],
  ])('offers no stop button when %s', (_label, state) => {
    renderCard({ maintenance: state });
    expect(screen.queryByTestId('wiki-maintain-cancel-button')).toBeNull();
  });

  it('offers to stop a stoppable run and asks the run to stop without passing anything along', async () => {
    const { maintenance } = renderCard({ maintenance: { isMaintaining: true, canCancelMaintain: true } });
    const stop = screen.getByTestId('wiki-maintain-cancel-button') as HTMLButtonElement;
    expect(stop.textContent).toBe('actions.maintainCancel');
    expect(stop.disabled).toBe(false);
    await click(stop);
    expect(maintenance.handleCancelMaintain).toHaveBeenCalledExactlyOnceWith();
  });

  it.each([
    ['cannot be stopped any more', { canCancelMaintain: false }],
    ['can still be stopped', { canCancelMaintain: true }],
  ])('shows a run that is being stopped as stopping, even if it %s', (_label, state) => {
    renderCard({ maintenance: { isMaintaining: true, isCancellingMaintain: true, ...state } });
    const stop = screen.getByTestId('wiki-maintain-cancel-button') as HTMLButtonElement;
    expect(stop.textContent).toBe('actions.maintainCancelling');
    expect(stop.disabled).toBe(true);
  });
});

describe('WikiActionsCard: repairs and reindexing', () => {
  it.each([
    ['page types', 'isRepairingTypes', 'actions.repairPageTypes', 'repairingTypes', 'handleRepairPageTypes'],
    [
      'publication state',
      'isRepairingPublication',
      'actions.repairPublication',
      'repairingPublication',
      'handleRepairPublication',
    ],
  ] as const)('repairs the %s', async (_label, flag, idle, busy, handler) => {
    const { maintenance } = renderCard();
    await click(button(idle));
    expect(maintenance[handler]).toHaveBeenCalledOnce();
    cleanup();
    renderCard({ maintenance: { [flag]: true } });
    expect(button(busy).disabled).toBe(true);
    expect(screen.queryByRole('button', { name: idle })).toBeNull();
  });

  it('reindexes the vectors without passing anything along', async () => {
    const { maintenance } = renderCard();
    await click(button('actions.reindexVectors'));
    expect(maintenance.handleReindexVectors).toHaveBeenCalledExactlyOnceWith();
  });

  it.each([
    ['running', { isReindexingVectors: true }, 'reindexingVectors'],
    ['blocked by a compile', { isWikiCompileBusy: true }, 'actions.reindexVectors'],
  ])('locks reindexing while it is %s', (_label, state, label) => {
    renderCard({ maintenance: state });
    expect(button(label).disabled).toBe(true);
  });

  it('leaves the other buttons usable while one repair runs', () => {
    renderCard({ maintenance: { isRepairingTypes: true } });
    expect(button('actions.repairPublication').disabled).toBe(false);
    expect(button('actions.reindexVectors').disabled).toBe(false);
  });
});

describe('WikiActionsCard: reindex errors', () => {
  const entries = (count: number) => Array.from({ length: count }, (_, index) => `file-${index}.md: failed`);

  it('shows no error box without errors', () => {
    renderCard();
    expect(screen.queryByTestId('wiki-reindex-errors')).toBeNull();
  });

  it('lists every error up to eight, with their count', () => {
    renderCard({ maintenance: { reindexErrors: entries(8) } });
    const box = within(screen.getByTestId('wiki-reindex-errors'));
    expect(box.getByText('reindexErrorsTitle|{"count":8}')).toBeTruthy();
    expect(box.getAllByRole('listitem').map((item) => item.textContent)).toEqual(entries(8));
    expect(box.queryByText(/^reindexErrorsTruncated/)).toBeNull();
  });

  it('lists the first eight errors and says how many more there are', () => {
    renderCard({ maintenance: { reindexErrors: entries(11) } });
    const box = within(screen.getByTestId('wiki-reindex-errors'));
    expect(box.getByText('reindexErrorsTitle|{"count":11}')).toBeTruthy();
    expect(box.getAllByRole('listitem').map((item) => item.textContent)).toEqual(entries(8));
    expect(box.getByText('reindexErrorsTruncated|{"count":3}')).toBeTruthy();
  });

  it('says one more when a single error is left out', () => {
    renderCard({ maintenance: { reindexErrors: entries(9) } });
    const box = within(screen.getByTestId('wiki-reindex-errors'));
    expect(box.getAllByRole('listitem')).toHaveLength(8);
    expect(box.getByText('reindexErrorsTruncated|{"count":1}')).toBeTruthy();
  });

  it('lists identical errors separately', () => {
    renderCard({ maintenance: { reindexErrors: ['same: failed', 'same: failed'] } });
    expect(within(screen.getByTestId('wiki-reindex-errors')).getAllByRole('listitem')).toHaveLength(2);
  });
});

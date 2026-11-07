/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BatchProjectDetailPage from '@/app/batch-directories/[projectId]/page';
import type { BatchProjectDetail, BatchProjectStatus } from '@/services/batch-directory';
import {
  TRIGGER,
  type TriggerKey,
  click,
  deferred,
  detailOf,
  dialog,
  queryTrigger,
  resetBatchMocks,
  serviceMocks,
  settle,
  startAction,
  toast,
  trigger,
} from './batchTestKit';

vi.mock('next-intl', () => import('./batchTestKit').then((m) => ({ useTranslations: () => m.t })));
vi.mock('next/navigation', () => import('./batchTestKit').then((m) => ({ useRouter: () => m.router })));
vi.mock('next/link', () => import('./batchTestKit').then((m) => ({ default: m.Link })));
vi.mock('@/hooks/shared/useToast', () => import('./batchTestKit').then((m) => ({ toast: m.toast })));
vi.mock('@/services/batch-directory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/batch-directory')>()),
  ...(await import('./batchTestKit')).serviceMocks,
}));

async function renderDetail(status: BatchProjectStatus, over: Partial<BatchProjectDetail> = {}) {
  serviceMocks.getBatchProject.mockResolvedValue(detailOf(status, over));
  const view = render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
  await settle();
  return view;
}

beforeEach(resetBatchMocks);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('BatchProjectToolbar visibility', () => {
  const VISIBLE: Record<BatchProjectStatus, TriggerKey[]> = {
    draft: ['approve', 'retry'],
    running: ['approve', 'retry', 'pause', 'cancel'],
    paused: ['approve', 'resume', 'cancel'],
    completed: ['retry', 'rerun', 'delete'],
    failed: ['retry', 'rerun', 'delete'],
    cancelled: ['retry', 'rerun', 'delete'],
  };

  it.each(Object.entries(VISIBLE) as [BatchProjectStatus, TriggerKey[]][])(
    'shows only the applicable actions for a %s project',
    async (status, visible) => {
      await renderDetail(status);
      expect(screen.getByRole('button', { name: 'refresh' })).toBeInTheDocument();
      for (const key of Object.keys(TRIGGER) as TriggerKey[]) {
        expect(queryTrigger(key) !== null, `${status}/${key}`).toBe(visible.includes(key));
      }
    },
  );

  it('hides approve-all without in-review tasks and retry without failed or missing-artifact directories', async () => {
    await renderDetail('running', { tasks: [], failed_directories: [], missing_artifact_directories: [] });
    expect(queryTrigger('approve')).toBeNull();
    expect(queryTrigger('retry')).toBeNull();
    expect(trigger('pause')).toBeInTheDocument();
  });

  it('puts the in-review count into the approve-all label and dialog title', async () => {
    await renderDetail('running');
    expect(trigger('approve')).toHaveTextContent('approveAllAction{"count":2}');
    await click(trigger('approve'));
    expect(dialog().getByText('confirmApproveAllTitle{"count":2}')).toBeInTheDocument();
  });

  it('refreshes the detail from the refresh button', async () => {
    await renderDetail('running');
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);
    await click(screen.getByRole('button', { name: 'refresh' }));
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(2);
  });
});

interface ActionCase {
  name: string;
  status: BatchProjectStatus;
  key: TriggerKey;
  confirm?: string;
  service: keyof typeof serviceMocks;
  result: Partial<BatchProjectDetail>;
  success: string;
  failure: string;
}

const ACTION_CASES: ActionCase[] = [
  {
    name: 'approve all',
    status: 'running',
    key: 'approve',
    confirm: 'confirmApproveAllAction',
    service: 'approveAllBatchResults',
    result: { approved_task_ids: ['a', 'b'] },
    success: 'approveAllSuccess{"count":2}',
    failure: 'approveAllError',
  },
  {
    name: 'retry',
    status: 'running',
    key: 'retry',
    service: 'retryBatchProject',
    result: { retried_task_ids: ['a'] },
    success: 'retrySuccess{"count":1}',
    failure: 'retryError',
  },
  {
    name: 'rerun',
    status: 'completed',
    key: 'rerun',
    confirm: 'confirmRerunAction',
    service: 'rerunBatchProject',
    result: { rerun_task_ids: ['a', 'b', 'c'] },
    success: 'rerunSuccess{"count":3}',
    failure: 'rerunError',
  },
  {
    name: 'pause',
    status: 'running',
    key: 'pause',
    confirm: 'confirmPauseAction',
    service: 'pauseBatchProject',
    result: {},
    success: 'pauseSuccess{"count":0}',
    failure: 'pauseError',
  },
  {
    name: 'resume',
    status: 'paused',
    key: 'resume',
    service: 'resumeBatchProject',
    result: { resumed_task_ids: ['a'] },
    success: 'resumeSuccess{"count":1}',
    failure: 'resumeError',
  },
  {
    name: 'cancel',
    status: 'running',
    key: 'cancel',
    confirm: 'confirmCancelAction',
    service: 'cancelBatchProject',
    result: {},
    success: 'cancelSuccess{"name":"Alpha"}',
    failure: 'cancelError',
  },
];

describe('BatchProjectActions project-level actions', () => {
  it.each(ACTION_CASES)(
    '$name: calls the service once, stays busy until done, then toasts and refreshes',
    async (action) => {
      const pending = deferred<BatchProjectDetail>();
      serviceMocks[action.service].mockReturnValue(pending.promise);
      await renderDetail(action.status);

      await startAction(action);
      expect(serviceMocks[action.service]).toHaveBeenCalledExactlyOnceWith('p1');
      expect(trigger(action.key)).toBeDisabled();
      expect(toast.success).not.toHaveBeenCalled();

      pending.resolve(detailOf(action.status, action.result));
      await settle();
      expect(toast.success).toHaveBeenCalledExactlyOnceWith(action.success);
      expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(2);
      expect(trigger(action.key)).toBeEnabled();
    },
  );

  it.each(ACTION_CASES)('$name: reports failure without refreshing', async (action) => {
    serviceMocks[action.service].mockRejectedValue(new Error('nope'));
    await renderDetail(action.status);

    await startAction(action);
    expect(toast.error).toHaveBeenCalledExactlyOnceWith(action.failure);
    expect(toast.success).not.toHaveBeenCalled();
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);
    expect(trigger(action.key)).toBeEnabled();
  });

  it.each(ACTION_CASES.filter((action) => action.confirm))(
    '$name: does nothing when the confirmation is dismissed',
    async (action) => {
      await renderDetail(action.status);
      await click(trigger(action.key));
      await click(dialog().getByRole('button', { name: 'cancelButton' }));
      expect(screen.queryByRole('alertdialog')).toBeNull();
      expect(serviceMocks[action.service]).not.toHaveBeenCalled();
    },
  );

  it('keeps the button busy until the refreshed detail arrives', async () => {
    serviceMocks.cancelBatchProject.mockResolvedValue(detailOf('running'));
    await renderDetail('running');
    const refreshed = deferred<BatchProjectDetail>();
    serviceMocks.getBatchProject.mockReturnValue(refreshed.promise);

    await startAction({ key: 'cancel', confirm: 'confirmCancelAction' });
    expect(toast.success).toHaveBeenCalledWith('cancelSuccess{"name":"Alpha"}');
    expect(trigger('cancel')).toBeDisabled();

    refreshed.resolve(detailOf('running'));
    await settle();
    expect(trigger('cancel')).toBeEnabled();
  });

  it('names the project in the confirmation dialogs', async () => {
    await renderDetail('running');
    await click(trigger('pause'));
    expect(dialog().getByText('confirmPauseTitle{"name":"Alpha"}')).toBeInTheDocument();
    await click(dialog().getByRole('button', { name: 'cancelButton' }));
    await click(trigger('cancel'));
    expect(dialog().getByText('confirmCancelTitle{"name":"Alpha"}')).toBeInTheDocument();
  });

  const LOCKS: {
    name: string;
    status: BatchProjectStatus;
    start: Pick<ActionCase, 'key' | 'confirm'> & { service: keyof typeof serviceMocks };
    disabled: TriggerKey[];
    enabled: TriggerKey[];
  }[] = [
    {
      name: 'pause',
      status: 'running',
      start: { key: 'pause', confirm: 'confirmPauseAction', service: 'pauseBatchProject' },
      disabled: ['approve', 'pause'],
      enabled: ['retry', 'cancel'],
    },
    {
      name: 'cancel',
      status: 'running',
      start: { key: 'cancel', confirm: 'confirmCancelAction', service: 'cancelBatchProject' },
      disabled: ['pause', 'cancel'],
      enabled: ['approve', 'retry'],
    },
    {
      name: 'resume',
      status: 'paused',
      start: { key: 'resume', service: 'resumeBatchProject' },
      disabled: ['approve', 'resume'],
      enabled: ['cancel'],
    },
    {
      name: 'cancel while paused',
      status: 'paused',
      start: { key: 'cancel', confirm: 'confirmCancelAction', service: 'cancelBatchProject' },
      disabled: ['resume', 'cancel'],
      enabled: ['approve'],
    },
    {
      name: 'approve all',
      status: 'running',
      start: { key: 'approve', confirm: 'confirmApproveAllAction', service: 'approveAllBatchResults' },
      disabled: ['approve'],
      enabled: ['pause', 'cancel', 'retry'],
    },
    {
      name: 'retry',
      status: 'completed',
      start: { key: 'retry', service: 'retryBatchProject' },
      disabled: ['retry'],
      enabled: ['rerun', 'delete'],
    },
    {
      name: 'rerun',
      status: 'completed',
      start: { key: 'rerun', confirm: 'confirmRerunAction', service: 'rerunBatchProject' },
      disabled: ['retry', 'rerun'],
      enabled: ['delete'],
    },
  ];

  it.each(LOCKS)('locks exactly the conflicting actions while $name is pending', async (lock) => {
    serviceMocks[lock.start.service].mockReturnValue(deferred<BatchProjectDetail>().promise);
    await renderDetail(lock.status);
    await startAction(lock.start);

    for (const key of lock.disabled) {
      expect(trigger(key), `${lock.name}: ${key} should be disabled`).toBeDisabled();
    }
    for (const key of lock.enabled) {
      expect(trigger(key), `${lock.name}: ${key} should be enabled`).toBeEnabled();
    }
  });
});

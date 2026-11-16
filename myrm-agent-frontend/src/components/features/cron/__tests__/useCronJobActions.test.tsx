/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { CronJob } from '@/services/cron.types';

import { useCronJobActions } from '../useCronJobActions';

const mocks = vi.hoisted(() => ({
  cronState: { pauseJob: vi.fn(), resumeJob: vi.fn(), triggerJob: vi.fn(), fetchJobs: vi.fn() },
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  // 翻译函数必须是稳定引用：每次渲染都新建会让依赖它的 hook 反复重建。
  translate: (key: string, params?: Record<string, string | number>) =>
    params ? `${key}|${Object.values(params).join(',')}` : key,
}));

vi.mock('next-intl', () => ({ useTranslations: () => mocks.translate }));
vi.mock('sonner', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));
vi.mock('@/services/cron', () => ({ duplicateCronJob: vi.fn() }));
vi.mock('@/store/useCronStore', () => ({
  default: (selector: (state: typeof mocks.cronState) => unknown) => selector(mocks.cronState),
}));

const JOB = { id: 'job-1', name: 'Daily digest', status: 'active', fire_count: 0 } as CronJob;

function renderActions() {
  const view = renderHook(() => useCronJobActions(JOB));
  const trigger = () => act(async () => view.result.current.handleTrigger());
  return { ...view, trigger };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.cronState.triggerJob.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useCronJobActions.handleTrigger', () => {
  it('confirms a started run and keeps the trigger locked for five seconds', async () => {
    vi.useFakeTimers();
    const { result, trigger } = renderActions();

    await trigger();

    expect(mocks.cronState.triggerJob).toHaveBeenCalledWith('job-1');
    expect(mocks.toastSuccess).toHaveBeenCalledWith('triggerSuccess|Daily digest');
    expect(mocks.toastError).not.toHaveBeenCalled();
    expect(result.current.triggering).toBe(true);

    await act(async () => vi.advanceTimersByTime(5_000));

    expect(result.current.triggering).toBe(false);
  });

  it('tells a task that is already running (409) from a failure, with one toast and the trigger free again', async () => {
    mocks.cronState.triggerJob.mockRejectedValue(new ApiError('Job is already running', 409));
    const { result, trigger } = renderActions();

    await trigger();

    expect(mocks.toastError).toHaveBeenCalledTimes(1);
    expect(mocks.toastError).toHaveBeenCalledWith('triggerAlreadyRunning|Daily digest');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(result.current.triggering).toBe(false);
  });

  it.each([
    ['a server error', new ApiError('boom', 500)],
    ['a missing task', new ApiError('Job not found or not active', 404)],
    ['a network failure', new Error('offline')],
  ])('reports %s as a failed trigger', async (_label, failure) => {
    mocks.cronState.triggerJob.mockRejectedValue(failure);
    const { result, trigger } = renderActions();

    await trigger();

    expect(mocks.toastError).toHaveBeenCalledTimes(1);
    expect(mocks.toastError).toHaveBeenCalledWith('triggerFail');
    expect(result.current.triggering).toBe(false);
  });

  it('ignores a second click while the first request is still settling', async () => {
    let finish: () => void = () => undefined;
    mocks.cronState.triggerJob.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    const { trigger } = renderActions();

    await act(async () => {
      void trigger();
    });
    await trigger();
    await act(async () => finish());

    expect(mocks.cronState.triggerJob).toHaveBeenCalledTimes(1);
  });
});

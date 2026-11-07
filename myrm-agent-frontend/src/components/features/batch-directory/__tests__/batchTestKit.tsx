import { act, fireEvent, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import type { BatchProject, BatchProjectDetail, BatchProjectStatus, BatchTaskItem } from '@/services/batch-directory';

/**
 * 批量目录测试共用工具：模块 mock 的实例、可序列化的 t、以及项目 / 任务夹具。
 * 各测试文件用 `vi.mock(path, () => import('./batchTestKit').then(...))` 挂接，确保页面与断言拿到同一批 mock。
 */

/** 返回稳定引用，避免依赖 t 的 effect / useCallback 每次渲染都重建；带插值参数时把参数拼进文案以便断言。 */
export const t = (key: string, values?: Record<string, unknown>) => (values ? `${key}${JSON.stringify(values)}` : key);

export const router = { push: vi.fn() };
export const toast = { success: vi.fn(), error: vi.fn() };

export const serviceMocks = {
  listBatchProjects: vi.fn(),
  getBatchProject: vi.fn(),
  createBatchProject: vi.fn(),
  cancelBatchProject: vi.fn(),
  deleteBatchProject: vi.fn(),
  retryBatchProject: vi.fn(),
  rerunBatchProject: vi.fn(),
  retryBatchTask: vi.fn(),
  pauseBatchProject: vi.fn(),
  resumeBatchProject: vi.fn(),
  approveAllBatchResults: vi.fn(),
};
export const listBoards = vi.fn();
export const browseDirectories = vi.fn();
export const isRiskHeldError = (e: unknown) => (e as { riskHeld?: boolean } | null)?.riskHeld === true;

export function Link({ href, children, ...rest }: { href: string; children: ReactNode }) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  );
}

export function resetBatchMocks() {
  [router.push, toast.success, toast.error, listBoards, browseDirectories, ...Object.values(serviceMocks)].forEach(
    (fn) => fn.mockReset(),
  );
  // Radix Switch / Checkbox 在 jsdom 中需要 ResizeObserver。
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}

/** 让已排队的 Promise 回调与随后的 React 更新落地。 */
export const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

export const click = async (el: Element) => {
  fireEvent.click(el);
  await settle();
};

export const typeInto = async (el: Element, value: string) => {
  fireEvent.change(el, { target: { value } });
  await settle();
};

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export const mkProject = (over: Partial<BatchProject> = {}): BatchProject => ({
  project_id: 'p1',
  name: 'Alpha',
  prompt: 'Run it',
  board_id: null,
  status: 'draft',
  concurrency: 3,
  agent_id: null,
  model_override: null,
  max_runtime_seconds: null,
  require_approval: false,
  notify_enabled: true,
  directories: ['/a', '/b'],
  artifact_patterns: [],
  total_tasks: 4,
  completed_tasks: 1,
  failed_tasks: 1,
  created_at: '2026-01-02T03:04:05Z',
  updated_at: null,
  started_at: null,
  finished_at: null,
  ...over,
});

export const mkTask = (over: Partial<BatchTaskItem> = {}): BatchTaskItem => ({
  task_id: 't1',
  title: 'Task',
  status: 'pending',
  workspace_path: '/a',
  agent_id: null,
  result: '',
  error: '',
  created_at: null,
  completed_at: null,
  ...over,
});

export const mkDetail = (over: Partial<BatchProjectDetail> = {}): BatchProjectDetail => ({
  ...mkProject({
    prompt: 'Run it',
    board_id: 'board-9',
    agent_id: 'agent-1',
    artifact_patterns: ['*.md'],
    directories: ['/a', '/b', '/c'],
    failed_directories: ['/b'],
    missing_artifact_directories: ['/c'],
    total_tasks: 4,
    completed_tasks: 1,
    failed_tasks: 1,
    started_at: '2026-01-02T03:04:05Z',
    finished_at: '2026-01-02T04:05:10Z',
  }),
  tasks: [],
  ...over,
});

/** 覆盖每种任务状态与结果形态；其中 4 个任务可重试（已归档、失败 ×2、产物缺失）。 */
export const DETAIL_TASKS: BatchTaskItem[] = [
  mkTask({
    task_id: 't-ok',
    title: 'Done verified',
    status: 'completed',
    artifact_status: 'verified',
    result: 'All good',
  }),
  mkTask({ task_id: 't-miss', title: 'Done missing', status: 'completed', artifact_status: 'missing' }),
  mkTask({ task_id: 't-bare', title: 'Done bare', status: 'completed', artifact_status: 'not_specified' }),
  mkTask({ task_id: 't-res', title: 'Done with result', status: 'completed', result: 'Some result text' }),
  mkTask({ task_id: 't-fail', title: 'Failed with msg', status: 'failed', error: 'boom' }),
  mkTask({ task_id: 't-fail2', title: 'Failed bare', status: 'failed' }),
  mkTask({ task_id: 't-run', title: 'Running', status: 'running' }),
  mkTask({ task_id: 't-arch', title: 'Archived', status: 'archived' }),
  mkTask({ task_id: 't-rev1', title: 'In review 1', status: 'in_review' }),
  mkTask({ task_id: 't-rev2', title: 'In review 2', status: 'in_review' }),
  mkTask({ task_id: 't-blk', title: 'Blocked', status: 'blocked' }),
  mkTask({ task_id: 't-pend', title: 'Pending', status: 'pending', workspace_path: null }),
  mkTask({ task_id: 't-weird', title: 'Weird', status: 'weird' }),
];

/** 详情页每个动作触发按钮的可访问名称（取消 / 删除等确认弹窗打开前的那一个）。 */
export const TRIGGER = {
  approve: /^approveAllAction/,
  retry: /^retryAction$/,
  rerun: /^rerunAction$/,
  pause: /^pauseAction$/,
  resume: /^resumeAction$/,
  cancel: /^cancelAction$/,
  delete: /^deleteAction$/,
} as const;
export type TriggerKey = keyof typeof TRIGGER;

export const detailOf = (status: BatchProjectStatus, over: Partial<BatchProjectDetail> = {}) =>
  mkDetail({ status, tasks: DETAIL_TASKS, total_tasks: 13, completed_tasks: 4, failed_tasks: 2, ...over });

export const trigger = (key: TriggerKey) => screen.getByRole('button', { name: TRIGGER[key] });
export const queryTrigger = (key: TriggerKey) => screen.queryByRole('button', { name: TRIGGER[key] });
export const retryTaskButtons = () => screen.getAllByRole('button', { name: /retryTaskAction/ });
export const taskRetryButton = (title: string) =>
  within(screen.getByText(title).closest('tr') as HTMLElement).getByRole('button', { name: /retryTaskAction/ });
export const dialog = () => within(screen.getByRole('alertdialog'));
export const confirmWith = (label: string) => click(dialog().getByRole('button', { name: label }));

/** 点击动作触发按钮；需要二次确认的动作继续点弹窗里的确认按钮。 */
export async function startAction({ key, confirm }: { key: TriggerKey; confirm?: string }) {
  await click(trigger(key));
  if (confirm) {
    await confirmWith(confirm);
  }
}

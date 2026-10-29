import { describe, it, expect, beforeEach } from 'vitest';
import { useCliPassthroughStore } from '../useCliPassthroughStore';

describe('useCliPassthroughStore', () => {
  beforeEach(() => {
    useCliPassthroughStore.getState().resetStore();
  });

  it('initializes with default empty state', () => {
    const state = useCliPassthroughStore.getState();
    expect(state.history).toEqual([]);
    expect(state.activeCommand).toBeNull();
    expect(state.isDrawerOpen).toBe(false);
    expect(state.isExecuting).toBe(false);
  });

  it('ignores non-CLI inputs and returns null', async () => {
    const res = await useCliPassthroughStore.getState().executeCommand('普通文本消息');
    expect(res).toBeNull();
    expect(useCliPassthroughStore.getState().history.length).toBe(0);
  });

  it('blocks dangerous command via safety guard and records blocked status', async () => {
    const blockedRecord = await useCliPassthroughStore.getState().executeCommand('! rm -rf /');
    expect(blockedRecord).toBeDefined();
    expect(blockedRecord?.status).toBe('blocked_by_guard');
    expect(blockedRecord?.exitCode).toBe(126);
    expect(blockedRecord?.guardReason).toContain('高危操作拦截');

    const state = useCliPassthroughStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.isExecuting).toBe(false);
    expect(state.history.length).toBe(1);
    expect(state.activeCommand?.id).toBe(blockedRecord?.id);
  });

  it('executes safe command successfully with default executor', async () => {
    const record = await useCliPassthroughStore.getState().executeCommand('!! git status');
    expect(record).toBeDefined();
    expect(record?.mode).toBe('user_inspection_only');
    expect(record?.status).toBe('success');
    expect(record?.exitCode).toBe(0);
    expect(record?.output).toContain('git status');

    const state = useCliPassthroughStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.isExecuting).toBe(false);
    expect(state.history.length).toBe(1);
  });

  it('executes command with custom executor and handles errors', async () => {
    const customExecutor = async () => {
      throw new Error('Sandbox network timeout');
    };

    const record = await useCliPassthroughStore.getState().executeCommand('! curl api.dev', customExecutor);
    expect(record).toBeDefined();
    expect(record?.mode).toBe('visible_to_context');
    expect(record?.status).toBe('failed');
    expect(record?.exitCode).toBe(1);
    expect(record?.output).toContain('Sandbox network timeout');
  });

  it('manages drawer toggle, item selection, and clearing history', async () => {
    await useCliPassthroughStore.getState().executeCommand('! npm run lint');
    await useCliPassthroughStore.getState().executeCommand('!! docker ps');

    const history = useCliPassthroughStore.getState().history;
    expect(history.length).toBe(2);

    const firstId = history[1].id;
    useCliPassthroughStore.getState().selectCommand(firstId);
    expect(useCliPassthroughStore.getState().activeCommand?.id).toBe(firstId);

    useCliPassthroughStore.getState().toggleDrawer(false);
    expect(useCliPassthroughStore.getState().isDrawerOpen).toBe(false);

    useCliPassthroughStore.getState().clearHistory();
    expect(useCliPassthroughStore.getState().history).toEqual([]);
    expect(useCliPassthroughStore.getState().activeCommand).toBeNull();
    expect(useCliPassthroughStore.getState().isDrawerOpen).toBe(false);
  });
});

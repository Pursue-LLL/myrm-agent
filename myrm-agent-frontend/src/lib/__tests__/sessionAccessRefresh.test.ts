import { beforeEach, describe, expect, it, vi } from 'vitest';

const getChatDetailMock = vi.fn();
const setSessionAccessRootsMock = vi.fn();

vi.mock('@/services/chat', () => ({
  getChatDetail: getChatDetailMock,
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      sessionAccessRoots: [{ path: '/existing', writable: false }],
      setSessionAccessRoots: setSessionAccessRootsMock,
    }),
  },
}));

describe('refreshSessionAccessRoots', () => {
  beforeEach(() => {
    getChatDetailMock.mockReset();
    setSessionAccessRootsMock.mockReset();
  });

  it('syncs roots from chat detail', async () => {
    getChatDetailMock.mockResolvedValue({
      chat: {
        session_access_roots: [{ path: '/data', writable: true, source: 'hitl_grant' }],
      },
    });

    const { refreshSessionAccessRoots } = await import('../sessionAccessRefresh');
    await refreshSessionAccessRoots('chat-1');

    expect(setSessionAccessRootsMock).toHaveBeenCalledWith([
      { path: '/data', writable: true, source: 'hitl_grant' },
    ]);
  });

  it('applies optimistic when GET returns empty roots', async () => {
    getChatDetailMock.mockResolvedValue({ chat: { session_access_roots: [] } });

    const { refreshSessionAccessRoots } = await import('../sessionAccessRefresh');
    await refreshSessionAccessRoots('chat-1', {
      optimistic: { path: '/tmp/new', writable: true, source: 'path_ask_grant' },
    });

    expect(setSessionAccessRootsMock).toHaveBeenCalledWith([
      { path: '/existing', writable: false },
      { path: '/tmp/new', writable: true, source: 'path_ask_grant' },
    ]);
  });
});

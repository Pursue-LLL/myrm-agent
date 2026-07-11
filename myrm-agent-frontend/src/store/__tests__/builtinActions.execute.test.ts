import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

const addPaneMock = vi.fn();
const stopMessageMock = vi.fn();
const showI18nToastMock = vi.fn();

vi.mock('@/store/useWorkspaceStore', () => ({
  default: { getState: () => ({ addPane: addPaneMock }) },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      chatId: 'test-chat-123',
      stopMessage: stopMessageMock,
      messages: [],
      loading: false,
      loadMessages: vi.fn(),
    }),
  },
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: (...args: unknown[]) => showI18nToastMock(...args),
}));

vi.mock('@/services/chat', () => ({
  compactChat: vi.fn(),
  focusFlushChat: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), dismiss: vi.fn() },
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: () => ({ yoloModeEnabled: false }),
    set: vi.fn(),
  }),
}));

import { buildBuiltinActions } from '@/store/builtinActions';

describe('builtin action execute functions', () => {
  let actions: ReturnType<typeof buildBuiltinActions>;

  beforeEach(() => {
    vi.clearAllMocks();
    actions = buildBuiltinActions();
  });

  describe('/new', () => {
    it('calls addPane and returns success', async () => {
      const newAction = actions.find((a) => a.name === 'new')!;
      const result = await newAction.execute('');
      expect(addPaneMock).toHaveBeenCalledOnce();
      expect(result).toEqual({ success: true, newInputValue: '' });
    });
  });

  describe('/stop', () => {
    it('calls stopMessage and shows toast', async () => {
      const stopAction = actions.find((a) => a.name === 'stop')!;
      const result = await stopAction.execute('');
      expect(stopMessageMock).toHaveBeenCalledOnce();
      expect(showI18nToastMock).toHaveBeenCalledWith(
        'commands.builtin.stopped',
        undefined,
        { type: 'info' },
      );
      expect(result).toEqual({ success: true, newInputValue: '' });
    });
  });

  describe('/stop with no active chat', () => {
    it('returns error when no chatId', async () => {
      const { default: useChatStore } = await import('@/store/useChatStore');
      const originalGetState = useChatStore.getState;
      (useChatStore as { getState: Mock }).getState = vi.fn(() => ({
        chatId: null,
        stopMessage: stopMessageMock,
      }));

      const stopAction = actions.find((a) => a.name === 'stop')!;
      const result = await stopAction.execute('');
      expect(result).toEqual({ success: false, error: 'No active chat' });
      expect(stopMessageMock).not.toHaveBeenCalled();

      (useChatStore as { getState: typeof originalGetState }).getState = originalGetState;
    });
  });

  describe('/model', () => {
    it('shows toast hint and returns success', async () => {
      const modelAction = actions.find((a) => a.name === 'model')!;
      const result = await modelAction.execute('');
      expect(showI18nToastMock).toHaveBeenCalledWith(
        'commands.builtin.modelHint',
        undefined,
        { type: 'info', duration: 4000 },
      );
      expect(result).toEqual({ success: true, newInputValue: '' });
    });
  });

  describe('/yolo', () => {
    it('toggles yolo mode with no args', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo');
      expect(result.success).toBe(true);
      expect(showI18nToastMock).toHaveBeenCalled();
    });

    it('enables yolo with explicit on', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo on');
      expect(result.success).toBe(true);
    });

    it('disables yolo with explicit off', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo off');
      expect(result.success).toBe(true);
    });

    it('parses timeout in seconds', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo 30');
      expect(result.success).toBe(true);
    });

    it('parses timeout in minutes', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo 5m');
      expect(result.success).toBe(true);
    });

    it('parses timeout in hours', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo 1h');
      expect(result.success).toBe(true);
    });

    it('falls back to toggle for invalid args', async () => {
      const yoloAction = actions.find((a) => a.name === 'yolo')!;
      const result = await yoloAction.execute('/yolo invalidarg');
      expect(result.success).toBe(true);
    });
  });

  describe('/compact with no active chat', () => {
    it('returns error when no chatId', async () => {
      const { default: useChatStore } = await import('@/store/useChatStore');
      const originalGetState = useChatStore.getState;
      (useChatStore as Record<string, unknown>).getState = vi.fn(() => ({
        chatId: null,
        loadMessages: vi.fn(),
        stopMessage: stopMessageMock,
      }));

      const compactAction = actions.find((a) => a.name === 'compact')!;
      const result = await compactAction.execute('/compact');
      expect(result).toEqual({ success: false, error: 'No active chat' });

      (useChatStore as Record<string, unknown>).getState = originalGetState;
    });
  });

  describe('/focus with no active chat', () => {
    it('returns error when no chatId', async () => {
      const { default: useChatStore } = await import('@/store/useChatStore');
      const originalGetState = useChatStore.getState;
      (useChatStore as Record<string, unknown>).getState = vi.fn(() => ({
        chatId: null,
        loadMessages: vi.fn(),
        resetSessionState: vi.fn(),
        stopMessage: stopMessageMock,
      }));

      const focusAction = actions.find((a) => a.name === 'focus')!;
      const result = await focusAction.execute('');
      expect(result).toEqual({ success: false, error: 'No active chat' });

      (useChatStore as Record<string, unknown>).getState = originalGetState;
    });
  });

  describe('all actions return ActionResult shape', () => {
    it('all execute functions return objects with success field', async () => {
      for (const action of actions) {
        const result = await action.execute('');
        expect(result).toHaveProperty('success');
        expect(typeof result.success).toBe('boolean');
      }
    });
  });
});

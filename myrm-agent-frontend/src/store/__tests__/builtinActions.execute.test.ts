import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

const addPaneMock = vi.fn();
const stopMessageMock = vi.fn();
const showI18nToastMock = vi.fn();

vi.mock('@/store/useWorkspaceStore', () => ({
  default: { getState: () => ({ addPane: addPaneMock, panes: [] }) },
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
  fetchWithTimeout: vi.fn(),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: () => ({ yoloModeEnabled: false }),
    set: vi.fn(),
  }),
}));

const setPetPaletteOpenMock = vi.fn();
const setSpriteEnabledMock = vi.fn();
const setSpriteConfigMock = vi.fn();
const saveConfigToServerMock = vi.fn().mockResolvedValue(undefined);

vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: {
    getState: () => ({
      isEnabled: (key: string) => key === 'companion_mode',
    }),
  },
}));

vi.mock('@/store/useCompanionStore', () => ({
  default: {
    getState: () => ({
      spriteEnabled: false,
      spriteConfig: { petSlug: 'nous-girl', displayName: 'Nous Girl' },
      setPetPaletteOpen: setPetPaletteOpenMock,
      setSpriteEnabled: setSpriteEnabledMock,
      setSpriteConfig: setSpriteConfigMock,
      saveConfigToServer: saveConfigToServerMock,
    }),
  },
}));

vi.mock('@/services/companion/petInstall', () => ({
  installCompanionPet: vi.fn(),
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
      (useChatStore as unknown as { getState: Mock }).getState = vi.fn(() => ({
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

  describe('/learn', () => {
    it('sends /learn message and shows started toast', async () => {
      const sendMessageMock = vi.fn().mockResolvedValue(undefined);
      const { default: useChatStore } = await import('@/store/useChatStore');
      const originalGetState = useChatStore.getState;
      (useChatStore as unknown as { getState: Mock }).getState = vi.fn(() => ({
        chatId: 'test-chat-123',
        loading: false,
        sendMessage: sendMessageMock,
      }));

      const learnAction = actions.find((a) => a.name === 'learn')!;
      const result = await learnAction.execute('/learn https://docs.example.com/api');

      expect(sendMessageMock).toHaveBeenCalledWith('/learn https://docs.example.com/api');
      expect(showI18nToastMock).toHaveBeenCalledWith('chat.extractToSkill.started', undefined, {
        type: 'info',
      });
      expect(result).toEqual({ success: true, newInputValue: '' });

      (useChatStore as { getState: typeof originalGetState }).getState = originalGetState;
    });

    it('bootstraps chat when no active chat and sends learn message', async () => {
      const sendMessageMock = vi.fn().mockResolvedValue(undefined);
      const initializeChatMock = vi.fn();
      const { default: useChatStore } = await import('@/store/useChatStore');
      const originalGetState = useChatStore.getState;
      (useChatStore as unknown as { getState: Mock }).getState = vi.fn(() => ({
        chatId: null,
        loading: false,
        sendMessage: sendMessageMock,
        initializeChat: initializeChatMock,
      }));
      initializeChatMock.mockImplementation(() => {
        (useChatStore as unknown as { getState: Mock }).getState = vi.fn(() => ({
          chatId: 'bootstrapped-chat',
          loading: false,
          sendMessage: sendMessageMock,
          initializeChat: initializeChatMock,
        }));
      });

      const learnAction = actions.find((a) => a.name === 'learn')!;
      const result = await learnAction.execute('/learn foo');

      expect(initializeChatMock).toHaveBeenCalledWith(undefined);
      expect(sendMessageMock).toHaveBeenCalledWith('/learn foo');
      expect(showI18nToastMock).toHaveBeenCalledWith('chat.extractToSkill.started', undefined, {
        type: 'info',
      });
      expect(result).toEqual({ success: true, newInputValue: '' });

      (useChatStore as { getState: typeof originalGetState }).getState = originalGetState;
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
      (useChatStore as unknown as Record<string, unknown>).getState = vi.fn(() => ({
        chatId: null,
        loadMessages: vi.fn(),
        stopMessage: stopMessageMock,
      }));

      const compactAction = actions.find((a) => a.name === 'compact')!;
      const result = await compactAction.execute('/compact');
      expect(result).toEqual({ success: false, error: 'No active chat' });

      (useChatStore as unknown as Record<string, unknown>).getState = originalGetState;
    });
  });

  describe('/pet', () => {
    it('opens pet palette for bare /pet', async () => {
      const petAction = actions.find((a) => a.name === 'pet')!;
      const result = await petAction.execute('/pet');
      expect(setPetPaletteOpenMock).toHaveBeenCalledWith(true);
      expect(result).toEqual({ success: true, newInputValue: '' });
    });

    it('opens pet palette for /pet list', async () => {
      const petAction = actions.find((a) => a.name === 'pet')!;
      const result = await petAction.execute('/pet list');
      expect(setPetPaletteOpenMock).toHaveBeenCalledWith(true);
      expect(result).toEqual({ success: true, newInputValue: '' });
    });

    it('toggles sprite overlay', async () => {
      const petAction = actions.find((a) => a.name === 'pet')!;
      const result = await petAction.execute('/pet toggle');
      expect(setSpriteEnabledMock).toHaveBeenCalledWith(true);
      expect(saveConfigToServerMock).toHaveBeenCalled();
      expect(result).toEqual({ success: true, newInputValue: '' });
    });

    it('installs pet by slug', async () => {
      const { installCompanionPet } = await import('@/services/companion/petInstall');
      (installCompanionPet as Mock).mockResolvedValue({
        slug: 'nous-girl',
        display_name: 'Nous Girl',
        content_sha256: 'abc123',
      });

      const petAction = actions.find((a) => a.name === 'pet')!;
      const result = await petAction.execute('/pet nous-girl');
      expect(installCompanionPet).toHaveBeenCalledWith('nous-girl');
      expect(setSpriteConfigMock).toHaveBeenCalledWith({
        petSlug: 'nous-girl',
        displayName: 'Nous Girl',
        contentSha256: 'abc123',
      });
      expect(setSpriteEnabledMock).toHaveBeenCalledWith(true);
      expect(result).toEqual({ success: true, newInputValue: '' });
    });
  });

  describe('/focus with no active chat', () => {
    it('returns error when no chatId', async () => {
      const { default: useChatStore } = await import('@/store/useChatStore');
      const originalGetState = useChatStore.getState;
      (useChatStore as unknown as Record<string, unknown>).getState = vi.fn(() => ({
        chatId: null,
        loadMessages: vi.fn(),
        resetSessionState: vi.fn(),
        stopMessage: stopMessageMock,
      }));

      const focusAction = actions.find((a) => a.name === 'focus')!;
      const result = await focusAction.execute('');
      expect(result).toEqual({ success: false, error: 'No active chat' });

      (useChatStore as unknown as Record<string, unknown>).getState = originalGetState;
    });
  });

  describe('all actions return ActionResult shape', () => {
    it('all execute functions return objects with success field', async () => {
      for (const action of actions) {
        if (action.name === 'goal') continue;
        const result = await action.execute('');
        expect(result).toHaveProperty('success');
        expect(typeof result.success).toBe('boolean');
      }
    });
  });
});

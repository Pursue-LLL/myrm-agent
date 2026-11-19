/**
 * The send guard decides on the search services only after they have synced, so an account whose list is still on its
 * way (or whose background load failed) is not told that search is unconfigured; an account that really has none is
 * still refused before any request.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/utils/toast';
import { setGlobalTranslator, showI18nToast } from '@/services/i18nToastService';
import { sendMessage, type ChatActionsMethods, type ChatActionsState } from '@/store/chat/messageRequest';
import type { ActionMode, AgentConfig } from '@/store/chat/types';
import useConfigStore from '@/store/useConfigStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const sync = vi.hoisted(() => ({ ensureSearchServicesLoaded: vi.fn<() => Promise<void>>() }));

vi.mock('@/store/config/searchService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/config/searchService')>();
  return { ...actual, ensureSearchServicesLoaded: sync.ensureSearchServicesLoaded };
});

// The turn stops at the model check right after the guard, so nothing here reaches the network.
vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

const CHAT_ID = 'chat-search-guard-wait';
const REQUEST_ID = 'r-1';
const SEARCH_SERVICE = {
  id: 'svc-1',
  enabled: true,
  priority: 1,
  search_service: 'tavily',
  api_key: 'key',
  createdAt: 1,
};

const agent = (agentId: string): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  agentId,
});

// The turn-end bookkeeping of a refused send.
const actions = {
  setMessages: vi.fn(),
  setHideAttachList: vi.fn(),
  scheduleAutoSave: vi.fn(),
} as unknown as ChatActionsMethods;

describe('sendMessage search guard', () => {
  const send = (actionMode: ActionMode, agentConfig: AgentConfig | null) =>
    sendMessage(
      'hello',
      REQUEST_ID,
      {
        chatId: CHAT_ID,
        actionMode,
        searchDepth: 'normal',
        agentConfig,
        abortController: null,
        loading: false,
        messages: [],
        files: [],
        mentionReferences: [],
        visionFrames: [],
        currentBuiltinTools: [],
        incognitoMode: false,
      } as unknown as ChatActionsState,
      actions,
      () => REQUEST_ID,
      () => REQUEST_ID,
    );

  beforeEach(() => {
    setGlobalTranslator((key: string) => key);
    useToolApprovalStore.getState().clearAll();
    useConfigStore.setState({ searchServiceConfigs: [] });
    vi.mocked(showI18nToast).mockClear();
    vi.spyOn(toast, 'warning').mockReturnValue(0);
    sync.ensureSearchServicesLoaded.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ['the fast search mode', 'fast', null],
    ['the Quick Search agent picked in agent mode', 'agent', agent('builtin-fast-search')],
  ] as const)('judges %s on the services it waited for', async (_name, actionMode, agentConfig) => {
    sync.ensureSearchServicesLoaded.mockImplementation(async () => {
      await Promise.resolve();
      useConfigStore.setState({ searchServiceConfigs: [SEARCH_SERVICE] });
    });

    await send(actionMode, agentConfig);

    expect(sync.ensureSearchServicesLoaded).toHaveBeenCalledTimes(1);
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('still refuses, after the wait, an account that has no search service', async () => {
    await expect(send('fast', null)).resolves.toBe(false);

    expect(toast.warning).toHaveBeenCalledTimes(1);
    expect(sync.ensureSearchServicesLoaded.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(toast.warning).mock.invocationCallOrder[0],
    );
  });

  it('does not wait for a turn that needs no search service', async () => {
    await send('agent', agent('builtin-general'));

    expect(sync.ensureSearchServicesLoaded).not.toHaveBeenCalled();
  });
});

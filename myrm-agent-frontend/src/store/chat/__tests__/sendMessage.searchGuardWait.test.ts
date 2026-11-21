/**
 * The send guard hands every turn that needs a search service to the search-service gate and honours its verdict: a
 * refused turn goes out as no request at all, a turn the gate lets through carries on to the model check, and a turn
 * that needs no search service never asks.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setGlobalTranslator, showI18nToast } from '@/services/i18nToastService';
import { sendMessage, type ChatActionsMethods, type ChatActionsState } from '@/store/chat/messageRequest';
import type { ActionMode, AgentConfig } from '@/store/chat/types';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const gate = vi.hoisted(() => ({ checkSearchServiceReady: vi.fn<() => Promise<boolean>>() }));

vi.mock('@/store/config/searchServiceReady', () => ({
  checkSearchServiceReady: gate.checkSearchServiceReady,
}));

// The turn stops at the model check right after the guard, so nothing here reaches the network.
vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

const CHAT_ID = 'chat-search-guard-wait';
const REQUEST_ID = 'r-1';
const MODEL_CHECK_TOAST = 'chat.modelNotConfigured.title';

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
    vi.mocked(showI18nToast).mockClear();
    gate.checkSearchServiceReady.mockReset().mockResolvedValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ['the fast search mode', 'fast', null],
    ['the Quick Search agent picked in agent mode', 'agent', agent('builtin-fast-search')],
  ] as const)(
    'carries %s on to the model check once the gate lets it through',
    async (_name, actionMode, agentConfig) => {
      await send(actionMode, agentConfig);

      expect(gate.checkSearchServiceReady).toHaveBeenCalledTimes(1);
      expect(showI18nToast).toHaveBeenCalledWith(MODEL_CHECK_TOAST, undefined, expect.anything());
    },
  );

  it('sends no request for a turn the gate refuses, and frees the message for the next send', async () => {
    gate.checkSearchServiceReady.mockResolvedValue(false);

    await expect(send('fast', null)).resolves.toBe(false);

    expect(gate.checkSearchServiceReady).toHaveBeenCalledTimes(1);
    expect(showI18nToast).not.toHaveBeenCalled();
    expect(useToolApprovalStore.getState().isProcessing(REQUEST_ID)).toBe(false);
  });

  it('does not ask the gate for a turn that needs no search service', async () => {
    await send('agent', agent('builtin-general'));

    expect(gate.checkSearchServiceReady).not.toHaveBeenCalled();
  });
});

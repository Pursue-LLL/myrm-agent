/**
 * [INPUT]
 * - @/store/chat/messageRequest::getModelSelection (POS: Facade of the chat message request layer.)
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useToolApprovalStore::useToolApprovalStore
 * - @/store/useConfigStore::useConfigStore
 * - @/store/config/searchService::guardSearchServiceConfigured
 * - @/store/chat/types::ActionMode, AgentConfig (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 * - @/components/dev/e2eBridge/e2eChatBridgeSendPolicy::shouldPreserveE2eActionMode, shouldRunPrepareAutomationSend (POS: Action-mode policy of an automated send: fast mode reaches the server as it is, agent-mode sends may be prepared.)
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend (POS: 开发桥的页面环境探针)
 * - @/components/dev/e2eBridge/sendTurnResult::E2eSubmitResult, buildSendTurnDiagnostic (POS: 一次发送的结果词汇)
 *
 * [OUTPUT]
 * - prepareTurn(request): every check and reset a send needs before the message is handed to the product; ends in a refusal result (nothing was sent) or the chat id and the agent-config override to send with
 * - TurnRequest / PreparedTurn
 *
 * [POS]
 * 发送流水线的发送前阶段：打开会话、写入输入、逐项校验并等聊天空闲、注入临时子智能体，任何一项不满足就以带 `mode` 的结果拒绝。
 */
import { flushSync } from 'react-dom';
import { getModelSelection } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useConfigStore from '@/store/useConfigStore';
import { guardSearchServiceConfigured } from '@/store/config/searchService';
import type { ActionMode, AgentConfig } from '@/store/chat/types';
import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '@/components/dev/e2eBridge/e2eChatBridgeSendPolicy';
import { prepareAutomationSend } from '@/components/dev/e2eBridge/hostEnv';
import { buildSendTurnDiagnostic, type E2eSubmitResult } from '@/components/dev/e2eBridge/sendTurnResult';

/** How long a send waits for the chat to load its messages, and then for a running stream to end. */
const READY_WAIT_MS = 30_000;
const READY_POLL_MS = 200;

export interface TurnRequest {
  /** The trimmed message text. */
  text: string;
  baselineUsers: number;
  preserveActionMode: boolean;
  ephemeralSubagents?: Record<string, unknown>;
}

export type PreparedTurn =
  | {
      ok: true;
      /** Never empty: a chat without an id refuses the send. */
      chatIdBeforeSend: string;
      agentConfigOverride: AgentConfig | undefined;
    }
  | { ok: false; result: E2eSubmitResult };

const refuse = (result: E2eSubmitResult): PreparedTurn => ({ ok: false, result });

function hasSendableContent(text: string): boolean {
  const { files, pendingExplicitSkillActivation } = useChatStore.getState();
  return Boolean(text) || (files?.length ?? 0) > 0 || Boolean(pendingExplicitSkillActivation);
}

/** Polls until `isReady` holds or `timeoutMs` pass; the caller looks at the state again, a timeout is not an error. */
async function waitUntil(isReady: () => boolean, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (isReady()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, READY_POLL_MS));
  }
}

/** Fast mode answers from the search service, so a send without a configured one is refused. */
function refuseUnconfiguredSearch(actionMode: ActionMode): E2eSubmitResult | null {
  if (actionMode !== 'fast') {
    return null;
  }
  const configs = useConfigStore.getState().searchServiceConfigs;
  if (guardSearchServiceConfigured(configs)) {
    return null;
  }
  return {
    ok: false,
    err: 'search-not-configured',
    mode: 'sendTurnSearchGuard',
    debug: {
      actionMode,
      searchCount: configs.length,
      enabledCount: configs.filter((item) => item.enabled).length,
    },
  };
}

/** The request id of the previous send must neither stay marked as processing nor stay on the chat. */
function releaseStaleRequest(): void {
  const staleRequestId = useChatStore.getState().currentSessionMessageId;
  if (staleRequestId) {
    useToolApprovalStore.getState().unmarkProcessing(staleRequestId);
  }
  useChatStore.getState().clearCurrentSessionMessageId();
}

/** Waits for the messages and for a running stream to end; null when the chat is idle, the refusal when it stays busy. */
async function refuseBusyChat(): Promise<E2eSubmitResult | null> {
  const isIdle = (): boolean => {
    const chatState = useChatStore.getState();
    return !chatState.loading && !chatState.abortController;
  };
  await waitUntil(() => {
    const loadedState = useChatStore.getState();
    return loadedState.isMessagesLoaded && !loadedState.loading;
  }, READY_WAIT_MS);
  await waitUntil(isIdle, READY_WAIT_MS);
  if (isIdle()) {
    return null;
  }
  return {
    ok: false,
    err: 'chat-still-busy',
    mode: 'sendTurnBusy',
    debug: {
      turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
      ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
    },
  };
}

/**
 * The agent config to send when ephemeral subagents are requested, undefined otherwise. It is handed to
 * `sendMessage` as its agent-config override instead of being written to the store: the request state is fixed on
 * entry, so the payload always carries `ephemeral_subagents` even when attach resets the store's `agentConfig`.
 */
function resolveAgentConfigOverride(
  ephemeralSubagents: Record<string, unknown> | undefined,
  preserveActionMode: boolean,
): AgentConfig | undefined {
  if (!ephemeralSubagents || Object.keys(ephemeralSubagents).length === 0) {
    return undefined;
  }
  // JIT delegation is an agent-mode flow: the backend drops ephemeral_subagents
  // when action_mode=fast (converter.py sets jit_subagents=None for fast search).
  // Chrome E2E profile can persist actionMode=fast in localStorage, so force agent.
  if (!preserveActionMode) {
    useChatStore.getState().setActionMode('agent');
  }
  const currentConfig = useChatStore.getState().agentConfig;
  const override = {
    ...((currentConfig ?? {}) as Partial<AgentConfig>),
    ephemeralSubagents,
  } as AgentConfig;
  window.__MYRM_E2E_EPH_APPLIED__ = {
    keys: Object.keys(ephemeralSubagents),
    at: Date.now(),
    forced: !currentConfig,
  };
  return override;
}

export async function prepareTurn({
  text,
  baselineUsers,
  preserveActionMode,
  ephemeralSubagents,
}: TurnRequest): Promise<PreparedTurn> {
  if (!hasSendableContent(text)) {
    return refuse({ ok: false, err: 'empty-message', mode: 'sendTurnEmpty' });
  }
  window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
  window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.();
  const { actionMode: sendActionMode } = useChatStore.getState();
  const shouldPreserveActionMode = shouldPreserveE2eActionMode(sendActionMode, preserveActionMode);
  const sessionOpts = shouldPreserveActionMode ? { preserveActionMode: true } : undefined;
  await window.__MYRM_E2E_CHAT__?.ensureChatSession?.(sessionOpts);
  flushSync(() => {
    useChatStore.getState().setInputMessage(text);
  });
  const chatIdBeforeSend = useChatStore.getState().chatId?.trim() || '';
  if (!chatIdBeforeSend) {
    return refuse({ ok: false, err: 'no-chat-id', mode: 'sendTurnNoChatId' });
  }
  const searchRefusal = refuseUnconfiguredSearch(useChatStore.getState().actionMode);
  if (searchRefusal) {
    return refuse(searchRefusal);
  }
  if (!window.__MYRM_E2E_CHAT__?.isSendReady?.()) {
    return refuse({
      ok: false,
      err: 'send-not-ready',
      mode: 'sendTurnNotReady',
      debug: window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
    });
  }
  releaseStaleRequest();
  const busyRefusal = await refuseBusyChat();
  if (busyRefusal) {
    return refuse(busyRefusal);
  }
  if (shouldRunPrepareAutomationSend(shouldPreserveActionMode)) {
    prepareAutomationSend();
  }
  useToolApprovalStore.getState().clearAll();
  const agentConfigOverride = resolveAgentConfigOverride(ephemeralSubagents, preserveActionMode);
  const { actionMode, agentConfig: storedConfig } = useChatStore.getState();
  if (!getModelSelection(actionMode, agentConfigOverride ?? storedConfig)) {
    return refuse({
      ok: false,
      err: 'model-selection-unavailable',
      mode: 'sendTurnValidateFailed',
      chatId: chatIdBeforeSend,
      debug: { phase: 'ARM', ...buildSendTurnDiagnostic(chatIdBeforeSend), baselineUsers },
    });
  }
  return { ok: true, chatIdBeforeSend, agentConfigOverride };
}

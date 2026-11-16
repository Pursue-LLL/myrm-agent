/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace state manager.)
 * - @/components/dev/e2eBridge/e2eChatBridgeSendPolicy::shouldPreserveE2eActionMode, shouldRunPrepareAutomationSend (POS: Action-mode policy of an automated send: fast mode reaches the server as it is, agent-mode sends may be prepared.)
 * - @/lib/utils/messageUtils::buildExplicitSkillWireMessage (POS: 消息文本清理和格式化工具集。)
 * - @/components/dev/e2eBridge/providerBootstrap::E2eChatSessionOpts, initProvidersForE2e (POS: 开发桥的 provider 与搜索服务引导)
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend, resolveChatIdFromLocation (POS: 开发桥的页面环境探针)
 * - @/components/dev/e2eBridge/turnProgress::bumpE2eSendGeneration (POS: 发送回合的进度读数)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createSessionMembers(): chat session setup and re-attach, composer input access, workflow switch and context-branch bookmark fork
 *
 * [POS]
 * 桥成员（聊天会话）：会话建立与重连、输入框读写、工作流开关与上下文分支书签。
 */
import { flushSync } from 'react-dom';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '@/components/dev/e2eBridge/e2eChatBridgeSendPolicy';
import { buildExplicitSkillWireMessage } from '@/lib/utils/messageUtils';
import { type E2eChatSessionOpts, initProvidersForE2e } from '@/components/dev/e2eBridge/providerBootstrap';
import { prepareAutomationSend, resolveChatIdFromLocation } from '@/components/dev/e2eBridge/hostEnv';
import { bumpE2eSendGeneration } from '@/components/dev/e2eBridge/turnProgress';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export function createSessionMembers(): E2eBridgeMembers {
  return {
    ensureChatSession: async (opts?: E2eChatSessionOpts) => {
      await initProvidersForE2e(opts);
      const preserveActionMode = shouldPreserveE2eActionMode(
        useChatStore.getState().actionMode,
        Boolean(opts?.preserveActionMode),
      );
      if (shouldRunPrepareAutomationSend(preserveActionMode)) {
        prepareAutomationSend();
      }
      if (!useChatStore.getState().chatId?.trim()) {
        // A page opened at /<chatId> is already bound to that chat by the route; minting a fresh local id here
        // would make the turn land in a new chat and leave the seeded one empty. Adopt the route's id instead.
        const routed = resolveChatIdFromLocation();
        flushSync(() => {
          useChatStore.getState().initializeChat(routed);
        });
      }
    },
    attachToChat: async (chatId: string) => {
      const id = chatId.trim();
      if (!id) {
        throw new Error('empty-chat-id');
      }
      await initProvidersForE2e();
      if (typeof window.__MYRM_E2E_RUNTIME_READY__ !== 'undefined') {
        await window.__MYRM_E2E_RUNTIME_READY__;
      }
      prepareAutomationSend();
      flushSync(() => {
        const state = useChatStore.getState();
        // `state.loading` must NOT force a reload: a live turn is streaming
        // store-injected state (routingTier from SSE), and a
        // forceReload would clear the store and rebuild it from a DB snapshot
        // that has not yet persisted the assistant message — losing the tier.
        // attachToChat below polls until `loading` clears instead.
        const needsForcedReload = state.chatId === id && (state.notFound || state.loadError || !state.isMessagesLoaded);
        if (needsForcedReload) {
          useChatStore.setState({
            notFound: false,
            loadError: false,
            isMessagesLoaded: false,
            loading: false,
          });
        }
        useChatStore.getState().initializeChat(id, { forceReload: needsForcedReload });
      });
      const configuredAttachMs = Number(window.__MYRM_E2E_ATTACH_TIMEOUT_MS__);
      const attachMs =
        Number.isFinite(configuredAttachMs) && configuredAttachMs >= 60_000 ? configuredAttachMs : 90_000;
      const deadline = Date.now() + attachMs;
      while (Date.now() < deadline) {
        const state = useChatStore.getState();
        if (state.chatId === id && state.isMessagesLoaded && !state.notFound && !state.loadError && !state.loading) {
          flushSync(() => {
            useChatStore.setState({
              messages: [...state.messages],
              isMessagesLoaded: true,
              loading: false,
              messageAppeared: true,
            });
          });
          window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId: id } }));
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
      const finalState = useChatStore.getState();
      if (
        finalState.chatId === id &&
        finalState.isMessagesLoaded &&
        !finalState.notFound &&
        !finalState.loadError &&
        !finalState.loading
      ) {
        window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId: id } }));
        return;
      }
      throw new Error(
        `attach-timeout chatId=${finalState.chatId} notFound=${finalState.notFound} loadError=${finalState.loadError} loaded=${finalState.isMessagesLoaded}`,
      );
    },
    pokeChatRouteRender: (chatId: string) => {
      const id = chatId.trim();
      if (!id) {
        return { ok: false, err: 'empty-chat-id' };
      }
      flushSync(() => {
        const state = useChatStore.getState();
        useChatStore.setState({
          chatId: id,
          isMessagesLoaded: true,
          loading: false,
          messageAppeared: true,
          notFound: false,
          loadError: false,
          messages: Array.isArray(state.messages) ? [...state.messages] : [],
        });
      });
      window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId: id } }));
      const next = useChatStore.getState();
      const routeReady =
        next.chatId === id &&
        next.isMessagesLoaded &&
        (next.messages.length > 0 || Boolean(next.compactedSummary?.trim()));
      return {
        ok: true,
        routeReady,
        msgCount: next.messages.length,
        hasSkeleton: Boolean(
          typeof document !== 'undefined' && document.querySelector('[data-testid="message-list-skeleton"]'),
        ),
      };
    },
    recoverHitlStream: async (chatId: string) => {
      const id = chatId.trim();
      if (!id) {
        return { ok: false, err: 'empty-chat-id' };
      }
      if (typeof window.__MYRM_E2E_RUNTIME_READY__ !== 'undefined') {
        await window.__MYRM_E2E_RUNTIME_READY__;
      }
      return useChatStore.getState().recoverHitlStream(id);
    },
    resetChat: () => {
      bumpE2eSendGeneration('resetChat');
      flushSync(() => {
        const { actionMode } = useChatStore.getState();
        if (!shouldPreserveE2eActionMode(actionMode)) {
          prepareAutomationSend();
        }
        useChatStore.getState().initializeChat(undefined);
      });
      // initializeChat(undefined) leaves a fresh unsaved session while the
      // URL still shows the previous /chat/<id>; navigate home so later
      // chat_id_from_path reads never track a stale (server-unknown) id.
      // Same window.location.assign precedent as forkContextBranch below.
      window.location.assign('/');
    },
    setInputMessage: (message: string) => {
      flushSync(() => {
        useChatStore.getState().setInputMessage(message);
      });
    },
    getInputMessage: () => useChatStore.getState().inputMessage,
    peekOutboundUserMessage: () => {
      const state = useChatStore.getState();
      const pending = state.pendingExplicitSkillActivation;
      const userText = state.inputMessage;
      if (pending) {
        return buildExplicitSkillWireMessage(pending, userText);
      }
      return userText;
    },
    clearStreamRequestMessageId: () => {
      useChatStore.getState().clearCurrentSessionMessageId();
    },
    setWorkflowMode: (enabled: boolean) => {
      useChatStore.getState().setIsWorkflowMode(enabled);
    },
    isWorkflowMode: () => useChatStore.getState().isWorkflowMode,
    getLastAssistantMessageId: () => {
      const assistants = useChatStore.getState().messages.filter((message) => message.role === 'assistant');
      return assistants[assistants.length - 1]?.messageId ?? null;
    },
    forkFirstContextBranchBookmark: async () => {
      const chatId = useChatStore.getState().chatId;
      if (!chatId) {
        return { ok: false as const, reason: 'no-chat-id' };
      }
      if (useChatStore.getState().loading) {
        return { ok: false as const, reason: 'streaming-blocked' };
      }
      const { forkContextBranch, listContextBranches } = await import('@/services/chat');
      const branches = await listContextBranches(chatId);
      const bookmark = branches[0];
      if (!bookmark?.branch_id) {
        return { ok: false as const, reason: 'no-bookmark', branchCount: branches.length };
      }
      try {
        const label = bookmark.label?.trim() || bookmark.snapshot_path.split(/[/\\]/).pop() || 'Snapshot branch';
        const result = await forkContextBranch(chatId, bookmark.branch_id, label);
        if (!result.new_chat_id) {
          return { ok: false as const, reason: 'missing-new-chat-id' };
        }
        useWorkspaceStore.getState().addPane(result.new_chat_id);
        const target = `/${result.new_chat_id}`;
        window.location.assign(target);
        return { ok: true as const, newChatId: result.new_chat_id, parentChatId: chatId };
      } catch (error) {
        return {
          ok: false as const,
          reason: 'fork-failed',
          error: error instanceof Error ? error.message : String(error),
        };
      }
    },
  } as E2eBridgeMembers;
}

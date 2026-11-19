/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useApprovalStore::useApprovalStore
 * - @/store/useBrowserTakeoverStore::useBrowserTakeoverStore (POS: Manages the state when Agent requests human takeover of the browser session.)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createBrowserTakeoverMembers(): trigger, snapshot, recover, dismiss and complete a browser takeover
 *
 * [POS]
 * 桥成员（浏览器接管）：触发、快照、恢复、放弃与带续跑的完成。
 */
import { flushSync } from 'react-dom';
import useChatStore from '@/store/useChatStore';
import useApprovalStore from '@/store/useApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export function createBrowserTakeoverMembers(): E2eBridgeMembers {
  return {
    triggerBrowserTakeover: (payload) => {
      flushSync(() => {
        useBrowserTakeoverStore.getState().requestTakeover({
          reason: payload.reason,
          messageId: payload.messageId ?? 'e2e-takeover-msg',
          ui_mode: payload.ui_mode ?? 'extension',
          auto_detect_completion: payload.auto_detect_completion ?? false,
          url: payload.url,
        });
      });
    },
    getBrowserTakeoverSnapshot: () => {
      const state = useBrowserTakeoverStore.getState();
      return {
        pending: state.pending,
        uiMode: state.uiMode,
        autoDetectCompletion: state.autoDetectCompletion,
        reason: state.reason,
        messageId: state.messageId || null,
      };
    },
    recoverPendingBrowserTakeover: async () => {
      const chatId = useChatStore.getState().chatId;
      const { fetchPendingApprovals } = await import('@/hooks/approval/usePendingApprovalsRecovery');
      const approvals = await fetchPendingApprovals();
      const matching = approvals.filter(
        (approval) =>
          approval.action_type === 'browser_takeover' &&
          approval.status === 'PENDING' &&
          (!chatId || approval.chat_id === chatId),
      );
      for (const approval of matching) {
        useApprovalStore.getState().openApproval(approval);
      }
      const snap = useBrowserTakeoverStore.getState();
      return {
        recovered: matching.length,
        pending: snap.pending,
        uiMode: snap.uiMode,
      };
    },
    dismissBrowserTakeover: () => {
      flushSync(() => {
        useBrowserTakeoverStore.getState().completeTakeover();
      });
    },
    completeBrowserTakeoverWithResume: async () => {
      const snap = useBrowserTakeoverStore.getState();
      if (!snap.pending) {
        return { ok: false, reason: 'not_pending' };
      }
      const storeMessageId = snap.messageId;
      const chatId = useChatStore.getState().chatId;
      flushSync(() => {
        useBrowserTakeoverStore.getState().completeTakeover();
      });
      const { resolveBrowserTakeoverMessageId } = await import('@/store/useApprovalStore');
      const resumeMessageId = resolveBrowserTakeoverMessageId(storeMessageId);
      let resumeStarted = false;
      if (resumeMessageId) {
        void useChatStore
          .getState()
          .sendMessage('', resumeMessageId, undefined, { action: 'completed', message: '' })
          .then(() => {
            console.log('[E2E_TAKEOVER_RESUME] fire-and-forget sendMessage settled');
          })
          .catch((error: unknown) => {
            console.error('[E2E_TAKEOVER_RESUME] fire-and-forget sendMessage failed', error);
          });
        resumeStarted = true;
      }
      return {
        ok: true,
        chatId: chatId ?? null,
        resumeMessageId: resumeMessageId ?? null,
        storeMessageId: storeMessageId ?? null,
        resumeStarted,
      };
    },
  } as E2eBridgeMembers;
}

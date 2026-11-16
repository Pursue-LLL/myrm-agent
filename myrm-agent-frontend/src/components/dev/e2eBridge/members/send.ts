/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useToolApprovalStore::useToolApprovalStore
 * - @/store/skill::useSkillStore
 * - @/components/dev/e2eBridge/e2eClarificationSkip::skipActiveClarification (POS: The skip of the CDP E2E bridge.)
 * - @/components/dev/e2eBridge/submitAndObserveTurn::submitAndObserveTurn (POS: 发送并观察一个聊天回合的流水线编排)
 * - @/components/dev/e2eBridge/sendTurnResult::E2eSubmitResult, SendTurnProfile (POS: 一次发送的结果词汇)
 * - @/components/dev/e2eBridge/hostEnv::requireE2eChatBridge (POS: 开发桥的页面环境探针)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createSendMembers(): message sends, sealed turn observation, steer nudge, turn snapshot and slash-skill catalog prefetch
 * - skipActiveClarificationForE2e: skip the waiting clarification card through the answer flow of its Skip button
 *
 * [POS]
 * 桥成员（发送）：发送、封口观察、steer 推送、回合快照、斜杠技能目录预取与澄清卡跳过。
 */
import { flushSync } from 'react-dom';
import useChatStore from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { useSkillStore } from '@/store/skill';
import { skipActiveClarification } from '@/components/dev/e2eBridge/e2eClarificationSkip';
import { submitAndObserveTurn } from '@/components/dev/e2eBridge/submitAndObserveTurn';
import type { E2eSubmitResult, SendTurnProfile } from '@/components/dev/e2eBridge/sendTurnResult';
import { requireE2eChatBridge } from '@/components/dev/e2eBridge/hostEnv';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

interface SendTurnOptions {
  baselineUserCount?: number;
  preserveActionMode?: boolean;
  profile?: SendTurnProfile;
  ephemeralSubagents?: Record<string, unknown>;
}

/** The text of a message; empty when it has none. */
const textOf = (message: { content?: string } | undefined): string => message?.content ?? '';

/** One send through the product pipeline; the result is also kept on the bridge as `lastSubmitResult`. */
async function runSend(text: string, opts?: SendTurnOptions): Promise<E2eSubmitResult> {
  const baselineUsers =
    typeof opts?.baselineUserCount === 'number'
      ? opts.baselineUserCount
      : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
  const profile = opts?.profile === 'read' ? 'read' : 'live';
  const result = await submitAndObserveTurn(
    text,
    baselineUsers,
    profile,
    opts?.preserveActionMode === true,
    opts?.ephemeralSubagents,
  );
  requireE2eChatBridge().lastSubmitResult = result;
  return result;
}

export function createSendMembers(): E2eBridgeMembers {
  return {
    submitSteerNudge: async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) {
        return { ok: false, err: 'empty-message' };
      }
      flushSync(() => {
        useChatStore.getState().setInputMessage(trimmed);
      });
      const storeOk = await useChatStore.getState().steerMessage(trimmed);
      if (storeOk) {
        flushSync(() => {
          useChatStore.getState().setInputMessage('');
        });
        return { ok: true, mode: 'steerStore' };
      }
      const buttons = [...document.querySelectorAll('button[aria-label]')];
      const steerBtn = buttons.find((btn) => {
        const label = String(btn.getAttribute('aria-label') || '').toLowerCase();
        return (
          label.includes('steer') || label.includes('guidance') || label.includes('转向') || label.includes('指导')
        );
      }) as HTMLButtonElement | undefined;
      if (steerBtn && !steerBtn.disabled) {
        steerBtn.click();
        return { ok: true, mode: 'steerClick' };
      }
      const baselineUsers = window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0;
      const result = await submitAndObserveTurn(trimmed, baselineUsers, 'live');
      return result.ok
        ? { ok: true, mode: 'steerSendFallback', detail: result }
        : { ok: false, err: 'steer-fallback-send-failed', detail: result };
    },
    sendChatMessage: async (text: string, opts?: SendTurnOptions) => {
      window.__MYRM_E2E_EPH_OPTS__ = {
        hasOpts: Boolean(opts),
        hasEph: Boolean(opts?.ephemeralSubagents),
        keys: opts?.ephemeralSubagents ? Object.keys(opts.ephemeralSubagents) : [],
        at: Date.now(),
      };
      return runSend(text, opts);
    },
    submitAndObserveTurn: runSend,
    handleSubmit: async () => {
      const resolveMessage = (): string => {
        const fromStore = useChatStore.getState().inputMessage.trim();
        if (fromStore) {
          return fromStore;
        }
        const input = document.querySelector('[data-chat-input]') as HTMLTextAreaElement | null;
        const fromDom = input?.value?.trim() ?? '';
        if (fromDom) {
          flushSync(() => {
            useChatStore.getState().setInputMessage(fromDom);
          });
          return fromDom;
        }
        return '';
      };
      const e2eBridge = window.__MYRM_E2E_CHAT__;
      const baselineUsers =
        typeof e2eBridge?._submitBaselineUsers === 'number'
          ? e2eBridge._submitBaselineUsers
          : (e2eBridge?.turnSnapshot?.().userCount ?? 0);
      const result = await submitAndObserveTurn(resolveMessage(), baselineUsers, 'live');
      requireE2eChatBridge().lastSubmitResult = result;
    },
    sendWorkflowTemplateRun: async (templateId: string, query: string, displayName?: string) => {
      const { submitWorkflowTemplateRun } = await import('@/lib/workflow/submitWorkflowTemplateRun');
      return submitWorkflowTemplateRun({
        templateId,
        query,
        displayName,
      });
    },
    turnSnapshot: () => {
      const state = useChatStore.getState();
      const users = state.messages.filter((message) => message.role === 'user');
      const assistants = state.messages.filter((message) => message.role === 'assistant');
      const lastAssistant = assistants[assistants.length - 1];
      const assistantText = textOf(lastAssistant);
      const pending = state.pendingExplicitSkillActivation;
      const boundSkillIds = state.agentConfig?.selectedSkillIds ?? [];
      const skillCatalog = useSkillStore.getState();
      const slashBoundSkillResolvedCount = boundSkillIds.length;
      return {
        chatId: state.chatId?.trim() || null,
        messageCount: state.messages.length,
        userCount: users.length,
        assistantCount: assistants.length,
        lastAssistantRoutingTier: lastAssistant?.routingTier ?? null,
        lastAssistantKeys: lastAssistant ? Object.keys(lastAssistant) : [],
        isStreaming: Boolean(state.loading || state.abortController),
        hasOk: /\bOK\b/i.test(assistantText),
        hasDone: /\bDONE\b/i.test(assistantText),
        hasCompletionSignal: /(?:\bOK\b|GOAL_OK|\bDONE\b)/i.test(assistantText),
        lastAssistantSample: assistantText.slice(0, 200),
        // Test-only: the shape of the last two messages, so an empty sample can be traced to
        // the store rather than guessed at.
        lastTwoMessages: state.messages.slice(-2).map((m) => ({
          role: m?.role,
          contentType: typeof m?.content,
          contentPreview: typeof m?.content === 'string' ? m.content.slice(0, 160) : null,
          keys: Object.keys(m ?? {}).slice(0, 18),
        })),
        // Test-only view: a tool-approval turn appends an empty assistant placeholder, so the
        // last assistant alone under-reports the visible answer.
        assistantSamples: assistants.slice(-4).map((m) => textOf(m).slice(0, 120)),
        lastAssistantHasDoneSkipped: /DONE-SKIPPED/i.test(assistantText),
        clarificationAnswered: lastAssistant?.clarification?.answered === true,
        toolApprovalQueueLen: useToolApprovalStore.getState().queue.length,
        pendingSkillNames: pending?.skillNames ?? [],
        pendingSkillInstruction: pending?.instruction ?? null,
        agentSelectedSkillCount: boundSkillIds.length,
        slashBoundSkillResolvedCount,
        slashSkillCatalogReady: boundSkillIds.length === 0 || slashBoundSkillResolvedCount === boundSkillIds.length,
        marketSkillCount: skillCatalog.marketSkills.length,
      };
    },
    prefetchSlashSkillCatalog: async () => {
      const store = useSkillStore.getState();
      await Promise.all([store.fetchMarketSkills(true), store.fetchLocalSkills()]);
      const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {
        marketSkillCount: 0,
        slashBoundSkillResolvedCount: 0,
        slashSkillCatalogReady: false,
      };
      return {
        marketSkillCount: snap.marketSkillCount ?? 0,
        slashBoundSkillResolvedCount: snap.slashBoundSkillResolvedCount ?? 0,
        slashSkillCatalogReady: snap.slashSkillCatalogReady === true,
        skillStoreError: useSkillStore.getState().error,
      };
    },
    toolApprovalSnapshot: () => ({
      queueLen: useToolApprovalStore.getState().queue.length,
      tools: useToolApprovalStore.getState().queue.map((row) => row.toolName),
      chatIds: useToolApprovalStore.getState().queue.map((row) => row.chatId),
    }),
    skipActiveClarificationForE2e: skipActiveClarification,
  } as E2eBridgeMembers;
}

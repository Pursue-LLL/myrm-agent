/**
 * [INPUT]
 * - @/store/useToolApprovalStore::useToolApprovalStore
 * - @/components/dev/e2eBridge/sendTurnContract::SEND_TURN_REV (POS: 发送回合中与 Python 端 dev_gate 契约逐值对应的常量)
 *
 * [OUTPUT]
 * - E2eSubmitResult / SendTurnProfile: what one send reports and the profile that labels it
 * - buildSendTurnDiagnostic(chatId): the page-side snapshot that a refused or failed send attaches to its `debug`
 *
 * [POS]
 * 一次发送的结果词汇：结果类型与失败结果共用的页面诊断快照，供发送前准备、观察与编排三个阶段共用。
 */
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { SEND_TURN_REV } from '@/components/dev/e2eBridge/sendTurnContract';

export type E2eSubmitResult = {
  ok: boolean;
  err?: string;
  chatId?: string | null;
  mode?: string;
  debug?: Record<string, unknown>;
};

export type SendTurnProfile = 'live' | 'read';

export function buildSendTurnDiagnostic(chatId: string): Record<string, unknown> {
  const processingIds = [...useToolApprovalStore.getState().processingMessageIds];
  return {
    rev: SEND_TURN_REV,
    turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null,
    provider: window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null,
    workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
    chatId,
    processingIds,
    approvalQueueLen: useToolApprovalStore.getState().queue.length,
  };
}

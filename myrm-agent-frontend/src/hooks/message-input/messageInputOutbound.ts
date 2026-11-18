/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/useScopedArtifactStore::useScopedArtifactStore (POS: 工件局部编辑选区)
 * - @/store/useArtifactPortalStore::useArtifactPortalStore (POS: 工件面板，持有尚未保存的编辑)
 * - @/lib/utils/messageUtils::buildExplicitSkillWireMessage (POS: 显式技能激活的线上消息格式)
 * - ./useMessageInputWikiEvidenceCore::recordChatWikiQueryAttempt, queuePendingChatWikiQuerySuccess (POS: Wiki 证据复问口径)
 *
 * [OUTPUT]
 * - composeOutboundUserMessage: 把显式技能激活与工件局部选区并入待发文本
 * - injectDirtyArtifacts: 把尚未保存的工件编辑附到消息末尾并清掉脏状态
 * - clearPendingExplicitSkillActivation: 发送后清掉待用的显式技能
 * - recordChatQueryMetric: 上报一次 chat 复问尝试
 * - confirmInstructionLanded: 运行中的轮次接收了指令后登记延迟确认的成功
 *
 * [POS]
 * 聊天输入提交前后对 store 的读写：与 React 状态无关，直发、steer、redirect、排队四条提交路径共用。
 */

import { buildExplicitSkillWireMessage } from '@/lib/utils/messageUtils';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import useChatStore from '@/store/useChatStore';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';
import { queuePendingChatWikiQuerySuccess, recordChatWikiQueryAttempt } from './useMessageInputWikiEvidenceCore';

export function composeOutboundUserMessage(rawInput: string): string {
  let outbound = rawInput;
  const pending = useChatStore.getState().pendingExplicitSkillActivation;
  if (pending) {
    outbound = buildExplicitSkillWireMessage(pending, outbound);
  }

  // 注入局部工件编辑选区语义 (Scoped Artifact)
  const scopedTarget = useScopedArtifactStore.getState().target;
  if (scopedTarget) {
    const scopeHeader = `[针对工件 "${scopedTarget.artifactName}" 的局部范围 (${scopedTarget.scopeLabel}) 定向编辑]`;
    const snippetBody = scopedTarget.selectedSnippet ? `\n\`\`\`\n${scopedTarget.selectedSnippet}\n\`\`\`\n` : '';
    outbound = `${scopeHeader}${snippetBody}\n${outbound}`.trim();
    useScopedArtifactStore.getState().clearTarget();
  }

  return outbound;
}

export function clearPendingExplicitSkillActivation(): void {
  if (useChatStore.getState().pendingExplicitSkillActivation) {
    useChatStore.getState().setPendingExplicitSkillActivation(null);
  }
}

// 获取并清理脏状态的 Artifacts，用于注入到消息中
export function injectDirtyArtifacts(message: string): string {
  const dirtyArtifacts = useArtifactPortalStore.getState().getDirtyArtifacts();
  const artifactIds = Object.keys(dirtyArtifacts);

  if (artifactIds.length === 0) {
    return message;
  }

  let injectedMessage = message;

  // 将所有脏状态的 Artifacts 注入到消息末尾
  for (const id of artifactIds) {
    const content = dirtyArtifacts[id];
    injectedMessage += `\n\n<edited_artifact id="${id}">\n${content}\n</edited_artifact>`;
    // 注入后清除脏状态
    useArtifactPortalStore.getState().clearDirtyState(id);
  }

  return injectedMessage;
}

export function recordChatQueryMetric(): void {
  const chatState = useChatStore.getState();
  recordChatWikiQueryAttempt(chatState.messages, chatState.chatId);
}

/** Registers the deferred wiki-evidence success for an instruction the running turn accepted (steer or redirect). */
export function confirmInstructionLanded(): void {
  const chatState = useChatStore.getState();
  const currentSessionMessageId =
    typeof chatState.getCurrentSessionMessageId === 'function' ? chatState.getCurrentSessionMessageId() : undefined;
  queuePendingChatWikiQuerySuccess(chatState.messages, chatState.chatId, currentSessionMessageId);
}

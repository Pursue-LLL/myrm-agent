/**
 * [INPUT]
 * @/services/chat::getChatDetail (POS: Chat API client)
 * @/lib/utils/agentConfigMapper::buildAgentConfig (POS: Agent→AgentConfig 标准映射)
 * @/store/useAgentStore::useAgentStore (POS: Agent catalog fetch)
 * @/store/useChatStore::useChatStore (POS: Active chat session store)
 *
 * [OUTPUT]
 * restoreAgentConfigFromChat: Re-bind store agentConfig from chat.agent_id.
 * finalizeAgentStreamTurn: After any agent-stream segment completes (or attach finds no active
 * stream), reconcile store with DB chat.agent_id.
 *
 * [POS]
 * Chat agent binding SSOT for store hydration. Callers: loadMessages, streamConsumer,
 * attachToChat, resumeApprovalStream, resumePlanConfirmStream.
 */

import { getChatDetail } from '@/services/chat';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import useAgentStore from '@/store/useAgentStore';
import useChatStore from '@/store/useChatStore';
import { useSkillStore } from '@/store/skill';

export async function restoreAgentConfigFromChat(
  chatId: string,
  agentId: string | null | undefined,
): Promise<void> {
  if (!agentId) {
    return;
  }

  const currentConfig = useChatStore.getState().agentConfig;
  if (currentConfig?.agentId === agentId) {
    return;
  }

  try {
    const agent = await useAgentStore.getState().fetchAgent(agentId);
    if (!agent) {
      console.warn('[MYRM-AGENT-RESTORE] fetchAgent returned empty', { chatId, agentId });
      return;
    }
    if (useChatStore.getState().chatId !== chatId) {
      console.warn('[MYRM-AGENT-RESTORE] chatId changed during restore', {
        chatId,
        agentId,
        stateChatId: useChatStore.getState().chatId,
      });
      return;
    }
    const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
    await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
    useChatStore.getState().setAgentConfig(buildAgentConfig(agent));
  } catch (error) {
    console.warn('[MYRM-AGENT-RESTORE] restoreAgentConfigFromChat failed', { chatId, agentId, error });
  }
}

export async function finalizeAgentStreamTurn(chatId: string | undefined): Promise<void> {
  const trimmed = chatId?.trim();
  if (!trimmed) {
    return;
  }

  const state = useChatStore.getState();
  if (state.actionMode !== 'agent' || state.chatId !== trimmed) {
    return;
  }

  try {
    const chatData = await getChatDetail(trimmed, true);
    await restoreAgentConfigFromChat(trimmed, chatData.chat.agent_id);
  } catch (error) {
    console.warn('[MYRM-AGENT-RESTORE] finalizeAgentStreamTurn failed', { chatId: trimmed, error });
  }
}

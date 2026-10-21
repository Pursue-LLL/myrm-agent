import { getAgent } from '@/services/agent';
import useChatStore from '@/store/useChatStore';

/**
 * When the server updates an agent profile (e.g. discovery adopt append), refresh
 * the in-session chat agentConfig allowlist if that agent is currently bound.
 */
export async function syncBoundChatAgentConfig(agentId: string): Promise<void> {
  const trimmed = agentId.trim();
  if (!trimmed) {
    return;
  }

  const chatState = useChatStore.getState();
  const boundId = chatState.agentConfig?.agentId?.trim();
  if (!boundId || boundId !== trimmed) {
    return;
  }

  const agent = await getAgent(trimmed, false);
  if (!agent) {
    return;
  }

  chatState.updateAgentConfig({
    selectedSkillIds: agent.skill_ids ?? [],
  });
}

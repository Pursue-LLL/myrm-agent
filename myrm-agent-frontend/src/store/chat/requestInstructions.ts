/**
 * [INPUT]
 * @/components/features/companion/companionGenerator (POS: Companion identity and personality)
 * ../useCompanionStore (POS: Companion on/off and naming)
 * @/store/chat/types::AgentConfig (POS: Chat-level agent configuration)
 *
 * [OUTPUT]
 * buildClientInstructions: The instruction text the client contributes to a chat turn.
 *
 * [POS]
 * The client's share of `user_instructions`: the global instruction and the companion intro. The agent's own system
 * prompt is not part of it; the server adds the prompt saved with the agent, or the chat-level
 * `agent_config.system_prompt` when the user rewrote it in this chat.
 */

import {
  generateCompanion,
  getEnhancedPersonality,
  getTitle,
  type Rarity,
} from '@/components/features/companion/companionGenerator';
import type { AgentConfig } from '@/store/chat/types';
import useCompanionStore from '../useCompanionStore';

const buildCompanionIntro = (userId: string | undefined): string => {
  const companionState = useCompanionStore.getState();
  if (!companionState.enabled || companionState.muted || !userId) {
    return '';
  }

  const bones = generateCompanion(userId);
  const name = companionState.nameOverride ?? bones.defaultName;
  const effectiveRarity = (companionState.evolvedRarity ?? bones.rarity) as Rarity;
  const personality = getEnhancedPersonality(bones, effectiveRarity);
  const title = getTitle(bones.peakStat, effectiveRarity);
  const displayName = title ? `${title} ${name}` : name;
  return `\n# Companion\nA ${effectiveRarity} ${bones.species} named ${displayName} sits beside the user. Personality: ${personality}. It's a separate observer with its own speech bubble — you are NOT ${name}. If the user addresses ${name}, respond in ≤1 line; don't narrate what ${name} might say.`;
};

export const buildClientInstructions = (
  isAgentMode: boolean,
  agentConfig: AgentConfig | null,
  systemInstructions: string,
  userId: string | undefined,
): string => {
  // An agent chat can opt out of the global instruction; every other chat always carries it.
  const includeGlobalInstruction = !isAgentMode || !agentConfig || agentConfig.useGlobalInstruction;
  return (includeGlobalInstruction ? systemInstructions || '' : '') + buildCompanionIntro(userId);
};

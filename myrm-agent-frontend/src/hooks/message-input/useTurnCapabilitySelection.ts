/**
 * [INPUT]
 * - ./turnCapabilityOverrideCore::TurnCapabilitySelection (POS: 本轮能力覆写的 Skill / MCP 子集)
 * - @/store/chat/types::AgentConfig (POS: 会话级 Agent 配置，提供能力基线)
 *
 * [OUTPUT]
 * - useTurnCapabilitySelection: 输入区暂存的「仅本轮」能力覆写及其消费
 *
 * [POS]
 * 聊天输入业务 Hook 的单轮能力部分：覆写只属于做出它的会话与能力基线，会话或基线一变就作废；提交时消费一次。
 */

import { useCallback, useEffect, useState } from 'react';
import type { AgentConfig } from '@/store/chat/types';
import type { TurnCapabilitySelection } from './turnCapabilityOverrideCore';

export function useTurnCapabilitySelection(chatId: string | undefined, agentConfig: AgentConfig | null) {
  const [turnCapabilitySelection, setTurnCapabilitySelection] = useState<TurnCapabilitySelection | null>(null);
  const agentSkillSignature = (agentConfig?.selectedSkillIds ?? []).join('\u0001');
  const agentMcpSignature = (agentConfig?.selectedMcpNames ?? []).join('\u0001');

  const consumeTurnCapabilitySelection = useCallback(() => {
    if (!turnCapabilitySelection) {
      return null;
    }
    const consumed = turnCapabilitySelection;
    setTurnCapabilitySelection(null);
    return consumed;
  }, [turnCapabilitySelection]);

  useEffect(() => {
    setTurnCapabilitySelection(null);
  }, [chatId, agentConfig?.agentId, agentSkillSignature, agentMcpSignature]);

  return { turnCapabilitySelection, setTurnCapabilitySelection, consumeTurnCapabilitySelection };
}

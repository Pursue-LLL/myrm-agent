'use client';

import { useEffect, useRef } from 'react';
import type { AgentConfig } from '@/store/chat/types';
import { buildAgentConfig } from '@/lib/utils/agent-config';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';

const GENERAL_AGENT_IDS = ['builtin-general', 'general'];
const FALLBACK_AGENT_ICON = 'MessageCircle';

function hasExistingAgentConfig(config: AgentConfig | null): boolean {
  if (!config) {
    return false;
  }
  return (
    (config.selectedMcpNames?.length ?? 0) > 0 ||
    (config.selectedSkillIds?.length ?? 0) > 0 ||
    (config.systemPrompt?.trim()?.length ?? 0) > 0 ||
    (config.autoRestoreDomains?.length ?? 0) > 0 ||
    !!config.agentId ||
    !!config.presetId
  );
}

/**
 * Selects the built-in general agent once on first load when the chat has no agent configuration yet.
 * An existing configuration (agent, skills, MCP servers, prompt, restore domains or preset) is never overwritten.
 */
export function useDefaultAgentBootstrap(setAgentConfig: (config: AgentConfig | null) => void): void {
  const hasInitializedRef = useRef(false);

  useEffect(() => {
    if (hasInitializedRef.current) {
      return;
    }
    hasInitializedRef.current = true;

    if (hasExistingAgentConfig(useChatStore.getState().agentConfig)) {
      return;
    }

    useAgentStore
      .getState()
      .fetchAgents()
      .then(async () => {
        const agents = useAgentStore.getState().agents;
        const generalAgent = agents.find((agent) => GENERAL_AGENT_IDS.includes(agent.id));
        if (!generalAgent) {
          return;
        }

        const presetIcon = generalAgent.avatar_url?.replace('icon:', '') || FALLBACK_AGENT_ICON;
        let config: AgentConfig = {
          agentId: generalAgent.id,
          selectedSkillIds: [],
          skillConfigs: {},
          selectedMcpNames: [],
          systemPrompt: '',
          useGlobalInstruction: true,
          autoRestoreDomains: [],
          presetId: generalAgent.id,
          presetName: generalAgent.name,
          presetIcon,
        };

        try {
          const fullAgent = await useAgentStore.getState().fetchAgent(generalAgent.id);
          if (fullAgent) {
            config = {
              ...buildAgentConfig(fullAgent),
              presetId: generalAgent.id,
              presetName: generalAgent.name,
              presetIcon,
            };
          }
        } catch (error) {
          console.error('Failed to fetch full agent details for general', error);
        }

        setAgentConfig(config);
      })
      .catch(console.error);
  }, [setAgentConfig]);
}

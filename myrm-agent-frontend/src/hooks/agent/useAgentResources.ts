import { useEffect, useMemo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import useAuthStore from '@/store/useAuthStore';
import useConfigStore from '@/store/useConfigStore';
import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';
import type { MCPServiceConfig } from '@/store/config/types';

export interface AgentResources {
  enabledSkills: Skill[];
  selectedSkillDetails: Skill[];
  selectedMcpDetails: MCPServiceConfig[];
  enabledMcps: MCPServiceConfig[];
}

export function useAgentResources(
  selectedSkillIds: string[],
  selectedMcpNames: string[],
  mountedSkillIds: string[] = [],
): AgentResources {
  const { user, isInitialized } = useAuthStore();

  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);
  const enabledMcps = useMemo(() => mcpConfigs.filter((m) => m.enabled), [mcpConfigs]);

  const {
    marketSkills,
    localSkills,
    isSkillEnabled,
    enabledPrebuiltIds,
    enabledLocalSkillIds,
    fetchMarketSkills,
    fetchUserSkillConfig,
  } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
      isSkillEnabled: state.isSkillEnabled,
      enabledPrebuiltIds: state.enabledPrebuiltIds,
      enabledLocalSkillIds: state.enabledLocalSkillIds,
      fetchMarketSkills: state.fetchMarketSkills,
      fetchUserSkillConfig: state.fetchUserSkillConfig,
    })),
  );

  const enabledSkills = useMemo(() => {
    const allSkills = [...marketSkills, ...localSkills];
    return allSkills.filter((skill) => isSkillEnabled(skill.id));
  }, [marketSkills, localSkills, isSkillEnabled, enabledPrebuiltIds, enabledLocalSkillIds]);

  const selectedSkillDetails = useMemo(() => {
    const allSkills = [...marketSkills, ...localSkills];
    return allSkills.filter((skill) => selectedSkillIds.includes(skill.id) || mountedSkillIds.includes(skill.id));
  }, [selectedSkillIds, mountedSkillIds, marketSkills, localSkills]);

  const selectedMcpDetails = useMemo(
    () => mcpConfigs.filter((mcp) => selectedMcpNames.includes(mcp.name)),
    [selectedMcpNames, mcpConfigs],
  );

  useEffect(() => {
    if (isInitialized && user) {
      fetchMarketSkills();
      fetchUserSkillConfig();
    }
  }, [isInitialized, user, fetchMarketSkills, fetchUserSkillConfig]);

  return {
    enabledSkills,
    selectedSkillDetails,
    selectedMcpDetails,
    enabledMcps,
  };
}

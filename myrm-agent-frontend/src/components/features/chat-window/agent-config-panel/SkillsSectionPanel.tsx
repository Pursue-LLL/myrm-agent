'use client';

import { useState, useMemo, useCallback } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Skill } from '@/store/skill/types';
import { useAgentNameMap } from '@/hooks/useAgentName';
import { AddMoreButton } from './AgentConfigSelectableCard';

import {
  NoiseGauge,
  CoreSkillsZone,
  PeripheralSkillsZone,
  MountedSkillsZone,
  AvailableSkillsZone,
} from './SkillsSectionPanelParts';

export interface SkillsSectionPanelProps {
  enabledSkills: Skill[];
  agentId?: string;
  localSkillIds: string[];
  setLocalSkillIds: React.Dispatch<React.SetStateAction<string[]>>;
  localMountedSkillIds: string[];
  setLocalMountedSkillIds: React.Dispatch<React.SetStateAction<string[]>>;
  localSkillConfigs: Record<string, { is_core?: boolean }>;
  setLocalSkillConfigs: React.Dispatch<React.SetStateAction<Record<string, { is_core?: boolean }>>>;
  noiseData: {
    isNoiseHigh: boolean;
    isNoiseCritical: boolean;
    noiseLevel: number;
    coreSkillsTokenCost: number;
    maxCoreTokens: number;
  };
  staleCoreSkills: string[];
  isSmartPruning?: boolean;
  onSmartPrune: () => void;
  onOpenSettingsSheet: (type: 'skills' | 'mcp') => void;
  t: (key: string) => string;
  tPanel: (key: string) => string;
}

export const SkillsSectionPanel = ({
  enabledSkills,
  agentId,
  localSkillIds,
  setLocalSkillIds,
  localMountedSkillIds,
  setLocalMountedSkillIds,
  localSkillConfigs,
  setLocalSkillConfigs,
  noiseData,
  staleCoreSkills,
  isSmartPruning = false,
  onSmartPrune,
  onOpenSettingsSheet,
  t,
  tPanel,
}: SkillsSectionPanelProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const { isNoiseHigh, isNoiseCritical, noiseLevel, coreSkillsTokenCost, maxCoreTokens } = noiseData;

  const filteredSkills = (enabledSkills || []).filter((s) => s.name.toLowerCase().includes(searchQuery.toLowerCase()));

  const isOwnSkill = useCallback(
    (skill: Skill) => !skill.scope_agent_id || skill.scope_agent_id === agentId,
    [agentId],
  );
  const isOtherSkill = useCallback(
    (skill: Skill) => !!(skill.scope_agent_id && skill.scope_agent_id !== agentId),
    [agentId],
  );

  const mountedOwnerIds = useMemo(() => {
    return (enabledSkills || [])
      .filter((s) => (localMountedSkillIds || []).includes(s.id) && s.scope_agent_id)
      .map((s) => s.scope_agent_id as string);
  }, [enabledSkills, localMountedSkillIds]);
  const agentNameMap = useAgentNameMap(mountedOwnerIds || []);

  const toggleSkill = (id: string) => {
    setLocalSkillIds((prev) => {
      const isSelected = prev.includes(id);
      if (!isSelected) {
        setLocalSkillConfigs((configs) => ({
          ...configs,
          [id]: { ...configs[id], is_core: true },
        }));
        return [...prev, id];
      }
      return prev.filter((x) => x !== id);
    });
  };

  const toggleMountedSkill = (id: string) => {
    setLocalMountedSkillIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleSkillCore = (id: string) => {
    setLocalSkillConfigs((configs) => {
      const currentIsCore = configs[id]?.is_core ?? true;
      return { ...configs, [id]: { ...configs[id], is_core: !currentIsCore } };
    });
  };

  if (enabledSkills.length === 0) {
    return (
      <div className="space-y-4">
        <div className="py-6 text-center">
          <p className="text-sm text-muted-foreground mb-3">{t('noEnabledSkills')}</p>
        </div>
        <AddMoreButton label={t('addMore')} onClick={() => onOpenSettingsSheet('skills')} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('searchPlaceholder')}
          className="pl-10 h-10 bg-muted/40 border-0 rounded-xl placeholder:text-muted-foreground/50 focus:bg-muted/60 transition-colors"
        />
      </div>

      <NoiseGauge
        isNoiseHigh={isNoiseHigh}
        isNoiseCritical={isNoiseCritical}
        noiseLevel={noiseLevel}
        coreSkillsTokenCost={coreSkillsTokenCost}
        maxCoreTokens={maxCoreTokens}
        staleCoreSkillCount={staleCoreSkills.length}
        isSmartPruning={isSmartPruning}
        onSmartPrune={onSmartPrune}
        tPanel={tPanel}
      />

      <div className="space-y-6 max-h-[400px] overflow-y-auto pr-1">
        <CoreSkillsZone
          filteredSkills={filteredSkills}
          localSkillIds={localSkillIds}
          localSkillConfigs={localSkillConfigs}
          isOwnSkill={isOwnSkill}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
        />
        <PeripheralSkillsZone
          filteredSkills={filteredSkills}
          localSkillIds={localSkillIds}
          localSkillConfigs={localSkillConfigs}
          isOwnSkill={isOwnSkill}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
        />
        <MountedSkillsZone
          filteredSkills={filteredSkills}
          localMountedSkillIds={localMountedSkillIds}
          isOtherSkill={isOtherSkill}
          agentNameMap={agentNameMap}
          toggleMountedSkill={toggleMountedSkill}
        />
        <AvailableSkillsZone
          filteredSkills={filteredSkills}
          localSkillIds={localSkillIds}
          localMountedSkillIds={localMountedSkillIds}
          isOwnSkill={isOwnSkill}
          isOtherSkill={isOtherSkill}
          agentNameMap={agentNameMap}
          toggleSkill={toggleSkill}
          toggleMountedSkill={toggleMountedSkill}
        />
      </div>

      <AddMoreButton label={t('addMore')} onClick={() => onOpenSettingsSheet('skills')} />
    </div>
  );
};


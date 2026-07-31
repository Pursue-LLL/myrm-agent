'use client';

import { useState, useCallback, useEffect } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Skill } from '@/store/skill/types';
import { AddMoreButton } from './AgentConfigSelectableCard';

import {
  NoiseGauge,
  CoreSkillsZone,
  PeripheralSkillsZone,
  AvailableSkillsZone,
} from './SkillsSectionPanelParts';
import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';

export interface SkillsSectionPanelProps {
  enabledSkills: Skill[];
  agentId?: string;
  localSkillIds: string[];
  setLocalSkillIds: React.Dispatch<React.SetStateAction<string[]>>;
  localSkillConfigs: AgentSkillConfigMap;
  setLocalSkillConfigs: React.Dispatch<React.SetStateAction<AgentSkillConfigMap>>;
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
  const [instancesBySkillName, setInstancesBySkillName] = useState<Record<string, string[]>>({});
  const { isNoiseHigh, isNoiseCritical, noiseLevel, coreSkillsTokenCost, maxCoreTokens } = noiseData;

  useEffect(() => {
    let cancelled = false;
    const selected = (enabledSkills || []).filter((s) => localSkillIds.includes(s.id));
    if (selected.length === 0) {
      setInstancesBySkillName({});
      return () => {
        cancelled = true;
      };
    }

    const load = async () => {
      const entries = await Promise.all(
        selected.map(async (skill) => {
          try {
            const response = await fetch(`/api/v1/skills/${encodeURIComponent(skill.name)}/instances`);
            if (!response.ok) {
              return [skill.name, []] as const;
            }
            const data = (await response.json()) as { instances?: string[] };
            return [skill.name, Array.isArray(data.instances) ? data.instances : []] as const;
          } catch {
            return [skill.name, []] as const;
          }
        }),
      );
      if (!cancelled) {
        setInstancesBySkillName(Object.fromEntries(entries));
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [enabledSkills, localSkillIds]);

  const filteredSkills = (enabledSkills || []).filter((s) => s.name.toLowerCase().includes(searchQuery.toLowerCase()));

  const isOwnSkill = useCallback(
    (skill: Skill) => !skill.scope_agent_id || skill.scope_agent_id === agentId,
    [agentId],
  );

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

  const toggleSkillCore = (id: string) => {
    setLocalSkillConfigs((configs) => {
      const currentIsCore = configs[id]?.is_core ?? true;
      return { ...configs, [id]: { ...configs[id], is_core: !currentIsCore } };
    });
  };

  const handleInstanceChange = (skillId: string, instanceName: string | null) => {
    setLocalSkillConfigs((configs) => ({
      ...configs,
      [skillId]: {
        ...configs[skillId],
        instance_name: instanceName,
      },
    }));
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
          onInstanceChange={handleInstanceChange}
          instancesBySkillName={instancesBySkillName}
          tPanel={tPanel}
        />
        <PeripheralSkillsZone
          filteredSkills={filteredSkills}
          localSkillIds={localSkillIds}
          localSkillConfigs={localSkillConfigs}
          isOwnSkill={isOwnSkill}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
          onInstanceChange={handleInstanceChange}
          instancesBySkillName={instancesBySkillName}
          tPanel={tPanel}
        />
        <AvailableSkillsZone
          filteredSkills={filteredSkills}
          localSkillIds={localSkillIds}
          isOwnSkill={isOwnSkill}
          toggleSkill={toggleSkill}
          tPanel={tPanel}
        />
      </div>

      <AddMoreButton label={t('addMore')} onClick={() => onOpenSettingsSheet('skills')} />
    </div>
  );
};

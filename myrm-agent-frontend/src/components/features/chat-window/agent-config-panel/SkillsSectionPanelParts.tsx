'use client';

import { Wand2, Sparkles, AlertTriangle, Info, Plus, Loader2, Wrench } from 'lucide-react';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';
import { Skill } from '@/store/skill/types';
import { SelectableCard } from './AgentConfigSelectableCard';
import { AgentSkillInstanceSelect } from './AgentSkillInstanceSelect';
import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';


export function NoiseGauge({
  isNoiseHigh,
  isNoiseCritical,
  noiseLevel,
  coreSkillsTokenCost,
  maxCoreTokens,
  staleCoreSkillCount,
  isSmartPruning = false,
  onSmartPrune,
  tPanel,
}: {
  isNoiseHigh: boolean;
  isNoiseCritical: boolean;
  noiseLevel: number;
  coreSkillsTokenCost: number;
  maxCoreTokens: number;
  staleCoreSkillCount: number;
  isSmartPruning?: boolean;
  onSmartPrune: () => void;
  tPanel: (key: string, values?: Record<string, string | number>) => string;
}) {
  const tRadar = (key: string, values?: Record<string, string | number>) =>
    tPanel(`actionSpaceRadar.${key}`, values);

  return (
    <div className="p-3 rounded-xl bg-muted/30 border border-border/50 space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground flex items-center gap-1.5">
          <Wand2 size={14} className="text-blue-500" />
          {tRadar('loadMeterLabel')}
        </span>
        <span
          className={cn(
            'font-mono text-xs',
            isNoiseCritical
              ? 'text-red-500 font-bold'
              : isNoiseHigh
                ? 'text-amber-500 font-bold'
                : 'text-muted-foreground',
          )}
        >
          ~{coreSkillsTokenCost} / {maxCoreTokens}
        </span>
      </div>
      <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full transition-all duration-300',
            isNoiseCritical ? 'bg-red-500' : isNoiseHigh ? 'bg-amber-500' : 'bg-green-500',
          )}
          style={{ width: `${noiseLevel}%` }}
        />
      </div>
      {isNoiseHigh && (
        <p className={cn('text-xs mt-1', isNoiseCritical ? 'text-red-500' : 'text-amber-500')}>
          <AlertTriangle size={16} className="inline mr-1 text-amber-500" />
          {isNoiseCritical ? tRadar('statusCritical') : tRadar('statusHigh')}
        </p>
      )}
      {staleCoreSkillCount > 0 && (
        <div className="mt-2 p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-start gap-2">
          <Info size={16} className="text-blue-500 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-xs text-blue-700 dark:text-blue-300">
              {tRadar('staleSkillsNotice', { count: staleCoreSkillCount })}
            </p>
            <button
              type="button"
              disabled={isSmartPruning}
              onClick={onSmartPrune}
              className={cn(
                'text-xs font-medium text-blue-600 dark:text-blue-400 mt-1 inline-flex items-center gap-1',
                isSmartPruning ? 'opacity-60 cursor-not-allowed' : 'hover:underline',
              )}
            >
              {isSmartPruning ? <Loader2 size={12} className="animate-spin" /> : null}
              {isSmartPruning ? tRadar('smartPruneRunning') : tRadar('smartPrune')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface SkillZoneProps {
  filteredSkills: Skill[];
  localSkillIds: string[];
  localSkillConfigs: AgentSkillConfigMap;
  isOwnSkill: (s: Skill) => boolean;
  toggleSkill: (id: string) => void;
  toggleSkillCore: (id: string) => void;
  onInstanceChange: (skillId: string, instanceName: string | null) => void;
  instancesBySkillName: Record<string, string[]>;
  tPanel: (key: string) => string;
}

export function SkillCard({
  skill,
  isCore,
  toggleSkill,
  toggleSkillCore,
  onInstanceChange,
  instanceName,
  instanceNames,
  icon,
  colorClass,
  rightElement,
}: {
  skill: Skill;
  isCore?: boolean;
  toggleSkill: (id: string) => void;
  toggleSkillCore?: (id: string) => void;
  onInstanceChange?: (instanceName: string | null) => void;
  instanceName?: string | null;
  instanceNames?: string[];
  icon: React.ReactNode;
  colorClass: string;
  rightElement?: React.ReactNode;
}) {
  const instancePicker =
    onInstanceChange != null ? (
      <AgentSkillInstanceSelect
        skillName={skill.name}
        value={instanceName ?? null}
        onChange={onInstanceChange}
        instances={instanceNames}
      />
    ) : null;

  const coreToggle =
    toggleSkillCore != null ? (
      <div
        className="flex items-center gap-2 px-2 py-1 bg-background/50 rounded-lg border border-border/50 no-card-click"
        onClick={(e) => {
          e.stopPropagation();
          toggleSkillCore(skill.id);
        }}
      >
        <span className={cn('text-[10px] font-medium', isCore ? 'text-blue-500' : 'text-muted-foreground')}>
          {isCore ? 'Core' : 'Peripheral'}
        </span>
        <Switch
          checked={isCore ?? false}
          onCheckedChange={() => toggleSkillCore(skill.id)}
          className="scale-75 data-[state=checked]:bg-blue-500"
        />
      </div>
    ) : null;

  const combinedRight = rightElement ?? (
    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
      {instancePicker}
      {coreToggle}
    </div>
  );

  return (
    <SelectableCard
      key={skill.id}
      id={`skill-${skill.id}`}
      label={skill.name}
      description={skill.description}
      checked={true}
      onCheckedChange={() => toggleSkill(skill.id)}
      icon={icon}
      colorClass={colorClass}
      rightElement={combinedRight}
    />
  );
}

export function CoreSkillsZone({
  filteredSkills,
  localSkillIds,
  localSkillConfigs,
  isOwnSkill,
  toggleSkill,
  toggleSkillCore,
  onInstanceChange,
  instancesBySkillName,
  tPanel,
}: SkillZoneProps) {
  const coreSkills = filteredSkills.filter(
    (s) => isOwnSkill(s) && localSkillIds.includes(s.id) && (localSkillConfigs[s.id]?.is_core ?? true),
  );
  if (coreSkills.length === 0) {return null;}

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 opacity-70" /> {tPanel('skillsZone.coreTitle')}
        </h4>
        <span className="text-[10px] text-muted-foreground">{tPanel('skillsZone.coreHint')}</span>
      </div>
      {coreSkills.map((skill) => (
        <SkillCard
          key={skill.id}
          skill={skill}
          isCore={true}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
          onInstanceChange={(instanceName) => onInstanceChange(skill.id, instanceName)}
          instanceName={localSkillConfigs[skill.id]?.instance_name ?? null}
          instanceNames={instancesBySkillName[skill.name]}
          icon={<Wand2 size={14} />}
          colorClass="text-blue-500"
        />
      ))}
    </div>
  );
}

export function PeripheralSkillsZone({
  filteredSkills,
  localSkillIds,
  localSkillConfigs,
  isOwnSkill,
  toggleSkill,
  toggleSkillCore,
  onInstanceChange,
  instancesBySkillName,
  tPanel,
}: SkillZoneProps) {
  const peripheralSkills = filteredSkills.filter(
    (s) => isOwnSkill(s) && localSkillIds.includes(s.id) && !(localSkillConfigs[s.id]?.is_core ?? true),
  );
  if (peripheralSkills.length === 0) {return null;}

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Wrench className="w-3.5 h-3.5 opacity-70" /> {tPanel('skillsZone.peripheralTitle')}
        </h4>
        <span className="text-[10px] text-muted-foreground">{tPanel('skillsZone.peripheralHint')}</span>
      </div>
      {peripheralSkills.map((skill) => (
        <SkillCard
          key={skill.id}
          skill={skill}
          isCore={false}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
          onInstanceChange={(instanceName) => onInstanceChange(skill.id, instanceName)}
          instanceName={localSkillConfigs[skill.id]?.instance_name ?? null}
          instanceNames={instancesBySkillName[skill.name]}
          icon={<Wand2 size={14} />}
          colorClass="text-blue-500"
        />
      ))}
    </div>
  );
}

export function AvailableSkillsZone({
  filteredSkills,
  localSkillIds,
  isOwnSkill,
  toggleSkill,
  tPanel,
}: {
  filteredSkills: Skill[];
  localSkillIds: string[];
  isOwnSkill: (s: Skill) => boolean;
  toggleSkill: (id: string) => void;
  tPanel: (key: string) => string;
}) {
  const available = filteredSkills.filter((s) => isOwnSkill(s) && !localSkillIds.includes(s.id));
  if (available.length === 0) {return null;}

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Plus className="w-3.5 h-3.5" /> {tPanel('skillsZone.availableTitle')}
        </h4>
      </div>
      {available.map((skill) => (
        <SelectableCard
          key={skill.id}
          id={`skill-${skill.id}`}
          label={skill.name}
          description={skill.description}
          checked={false}
          onCheckedChange={() => toggleSkill(skill.id)}
          icon={<Wand2 size={14} />}
          colorClass="text-blue-500"
        />
      ))}
    </div>
  );
}

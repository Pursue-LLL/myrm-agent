'use client';

import { useState, useMemo, useCallback } from 'react';
import { Wand2, Search, Plus, Bot, Link2, Layers, Sparkles, AlertTriangle, Info } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';
import { Skill } from '@/store/skill/types';
import { useAgentNameMap } from '@/hooks/useAgentName';
import { AddMoreButton, SelectableCard } from './AgentConfigSelectableCard';

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
  onSmartPrune,
  onOpenSettingsSheet,
  t,
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
        onSmartPrune={onSmartPrune}
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

/* ─── sub-components ─── */

function NoiseGauge({
  isNoiseHigh,
  isNoiseCritical,
  noiseLevel,
  coreSkillsTokenCost,
  maxCoreTokens,
  staleCoreSkillCount,
  onSmartPrune,
}: {
  isNoiseHigh: boolean;
  isNoiseCritical: boolean;
  noiseLevel: number;
  coreSkillsTokenCost: number;
  maxCoreTokens: number;
  staleCoreSkillCount: number;
  onSmartPrune: () => void;
}) {
  return (
    <div className="p-3 rounded-xl bg-muted/30 border border-border/50 space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground flex items-center gap-1.5">
          <Wand2 size={14} className="text-blue-500" />
          认知负载 (核心技能 Token)
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
          {isNoiseCritical
            ? '核心技能过多，将严重干扰模型注意力，请精简！'
            : '认知负载较高，建议将部分技能设为外围技能。'}
        </p>
      )}
      {staleCoreSkillCount > 0 && (
        <div className="mt-2 p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-start gap-2">
          <Info size={16} className="text-blue-500 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-xs text-blue-700 dark:text-blue-300">
              发现 {staleCoreSkillCount} 个闲置核心技能（30天未调用）。
            </p>
            <button
              onClick={onSmartPrune}
              className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline mt-1"
            >
              一键降级为外围技能，释放认知负载
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
  localSkillConfigs: Record<string, { is_core?: boolean }>;
  isOwnSkill: (s: Skill) => boolean;
  toggleSkill: (id: string) => void;
  toggleSkillCore: (id: string) => void;
}

function SkillCard({
  skill,
  isCore,
  toggleSkill,
  toggleSkillCore,
  icon,
  colorClass,
  rightElement,
}: {
  skill: Skill;
  isCore?: boolean;
  toggleSkill: (id: string) => void;
  toggleSkillCore?: (id: string) => void;
  icon: React.ReactNode;
  colorClass: string;
  rightElement?: React.ReactNode;
}) {
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
      rightElement={
        rightElement ??
        (toggleSkillCore ? (
          <div
            className="flex items-center gap-2 px-2 py-1 bg-background/50 rounded-lg border border-border/50 no-card-click"
            onClick={(e) => {
              e.stopPropagation();
              toggleSkillCore(skill.id);
            }}
          >
            <span className={cn('text-[10px] font-medium', isCore ? 'text-blue-500' : 'text-muted-foreground')}>
              {isCore ? '核心 (Core)' : '外围 (Peripheral)'}
            </span>
            <Switch
              checked={isCore ?? false}
              onCheckedChange={() => toggleSkillCore(skill.id)}
              className="scale-75 data-[state=checked]:bg-blue-500"
            />
          </div>
        ) : undefined)
      }
    />
  );
}

function CoreSkillsZone({ filteredSkills, localSkillIds, localSkillConfigs, isOwnSkill, toggleSkill, toggleSkillCore }: SkillZoneProps) {
  const coreSkills = filteredSkills.filter(
    (s) => isOwnSkill(s) && localSkillIds.includes(s.id) && (localSkillConfigs[s.id]?.is_core ?? true),
  );
  if (coreSkills.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 opacity-70" /> 核心常驻区 (Core)
        </h4>
        <span className="text-[10px] text-muted-foreground">完整注入，极速响应</span>
      </div>
      {coreSkills.map((skill) => (
        <SkillCard
          key={skill.id}
          skill={skill}
          isCore={true}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
          icon={<Wand2 size={14} />}
          colorClass="text-blue-500"
        />
      ))}
    </div>
  );
}

function PeripheralSkillsZone({ filteredSkills, localSkillIds, localSkillConfigs, isOwnSkill, toggleSkill, toggleSkillCore }: SkillZoneProps) {
  const peripheralSkills = filteredSkills.filter(
    (s) => isOwnSkill(s) && localSkillIds.includes(s.id) && !(localSkillConfigs[s.id]?.is_core ?? true),
  );
  if (peripheralSkills.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <span>🧰</span> 外围工具箱 (Peripheral)
        </h4>
        <span className="text-[10px] text-muted-foreground">按需加载，极低负担</span>
      </div>
      {peripheralSkills.map((skill) => (
        <SkillCard
          key={skill.id}
          skill={skill}
          isCore={false}
          toggleSkill={toggleSkill}
          toggleSkillCore={toggleSkillCore}
          icon={<Wand2 size={14} />}
          colorClass="text-blue-500"
        />
      ))}
    </div>
  );
}

function MountedSkillsZone({
  filteredSkills,
  localMountedSkillIds,
  isOtherSkill,
  agentNameMap,
  toggleMountedSkill,
}: {
  filteredSkills: Skill[];
  localMountedSkillIds: string[];
  isOtherSkill: (s: Skill) => boolean;
  agentNameMap: Map<string, string | undefined>;
  toggleMountedSkill: (id: string) => void;
}) {
  const mounted = filteredSkills.filter((s) => isOtherSkill(s) && localMountedSkillIds.includes(s.id));
  if (mounted.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Link2 className="w-3.5 h-3.5" /> 挂载技能 (Mounted)
        </h4>
        <span className="text-[10px] text-muted-foreground">来自其他智能体的跨域共享能力</span>
      </div>
      {mounted.map((skill) => {
        const ownerName = skill.scope_agent_id ? agentNameMap.get(skill.scope_agent_id) : undefined;
        return (
          <SelectableCard
            key={skill.id}
            id={`skill-mounted-${skill.id}`}
            label={skill.name}
            description={skill.description}
            checked={true}
            onCheckedChange={() => toggleMountedSkill(skill.id)}
            icon={<Layers size={14} />}
            colorClass="text-purple-500"
            rightElement={
              <div className="flex items-center gap-2">
                {ownerName && (
                  <div className="px-2 py-1 bg-purple-500/10 rounded-lg border border-purple-500/20 flex items-center gap-1">
                    <Bot className="w-3 h-3 text-purple-500" />
                    <span className="text-[10px] font-medium text-purple-600 dark:text-purple-400">{ownerName}</span>
                  </div>
                )}
                <div className="px-2 py-1 bg-background/50 rounded-lg border border-border/50">
                  <span className="text-[10px] font-medium text-purple-500">挂载中</span>
                </div>
              </div>
            }
          />
        );
      })}
    </div>
  );
}

function AvailableSkillsZone({
  filteredSkills,
  localSkillIds,
  localMountedSkillIds,
  isOwnSkill,
  isOtherSkill,
  agentNameMap,
  toggleSkill,
  toggleMountedSkill,
}: {
  filteredSkills: Skill[];
  localSkillIds: string[];
  localMountedSkillIds: string[];
  isOwnSkill: (s: Skill) => boolean;
  isOtherSkill: (s: Skill) => boolean;
  agentNameMap: Map<string, string | undefined>;
  toggleSkill: (id: string) => void;
  toggleMountedSkill: (id: string) => void;
}) {
  const available = filteredSkills.filter((s) =>
    isOwnSkill(s) ? !localSkillIds.includes(s.id) : !localMountedSkillIds.includes(s.id),
  );
  if (available.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 mb-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Plus className="w-3.5 h-3.5" /> 可选技能
        </h4>
      </div>
      {available.map((skill) => {
        const isMountable = isOtherSkill(skill);
        const ownerName = isMountable && skill.scope_agent_id ? agentNameMap.get(skill.scope_agent_id) : undefined;
        return (
          <SelectableCard
            key={skill.id}
            id={`skill-${skill.id}`}
            label={skill.name}
            description={skill.description}
            checked={false}
            onCheckedChange={() => (isMountable ? toggleMountedSkill(skill.id) : toggleSkill(skill.id))}
            icon={isMountable ? <Layers size={14} /> : <Wand2 size={14} />}
            colorClass={isMountable ? 'text-purple-500' : 'text-blue-500'}
            rightElement={
              isMountable ? (
                <div className="flex items-center gap-2">
                  {ownerName && (
                    <div className="px-2 py-1 bg-purple-500/10 rounded-lg border border-purple-500/20 flex items-center gap-1">
                      <Bot className="w-3 h-3 text-purple-500" />
                      <span className="text-[10px] font-medium text-purple-600 dark:text-purple-400">{ownerName}</span>
                    </div>
                  )}
                  <div className="px-2 py-1 bg-muted/50 rounded-lg border border-border/50">
                    <span className="text-[10px] font-medium text-muted-foreground">可挂载</span>
                  </div>
                </div>
              ) : undefined
            }
          />
        );
      })}
    </div>
  );
}

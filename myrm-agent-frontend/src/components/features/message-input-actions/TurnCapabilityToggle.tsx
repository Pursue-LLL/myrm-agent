'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/skill/useSkillStore::useSkillStore (POS: 技能状态与元数据管理)
 * - @/store/useConfigStore::useConfigStore (POS: 配置状态管理)
 * - @/hooks/message-input/turnCapabilityOverrideCore::* (POS: 本轮能力覆写归一化与覆盖构建核心)
 *
 * [OUTPUT]
 * - TurnCapabilityToggle: 输入区“下一条消息能力范围”单轮覆写交互组件。
 *
 * [POS]
 * 消息输入区的单轮能力选择视图层。为用户提供下一条消息的 Skill/MCP 子集选择，并保持仅本轮生效。
 */
import { useCallback, useMemo, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import { normalizeMCPServiceConfigs } from '@/lib/utils/mcpConfigNormalizer';
import {
  normalizeTurnCapabilitySelection,
  resolveEffectiveTurnSelection,
  type TurnCapabilitySelection,
} from '@/hooks/message-input/turnCapabilityOverrideCore';
import useChatStore from '@/store/useChatStore';
import useSkillStore from '@/store/skill/useSkillStore';
import useConfigStore from '@/store/useConfigStore';

interface CapabilityOption {
  id: string;
  label: string;
}

interface TurnCapabilityToggleProps {
  selection: TurnCapabilitySelection | null;
  onSelectionChange: (selection: TurnCapabilitySelection | null) => void;
  disabled?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
}

function CapabilityRow({
  label,
  active,
  onClick,
  disabled,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors',
        'hover:bg-muted/50 disabled:opacity-50',
        !active && 'opacity-50',
      )}
    >
      <div
        className={cn(
          'w-3.5 h-3.5 rounded-sm border flex-shrink-0 flex items-center justify-center transition-colors',
          active ? 'bg-primary border-primary' : 'border-border',
        )}
      >
        {active && (
          <svg width="10" height="8" viewBox="0 0 10 8" fill="none" aria-hidden="true">
            <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
      <span className="truncate">{label}</span>
    </button>
  );
}

export default function TurnCapabilityToggle({
  selection,
  onSelectionChange,
  disabled = false,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  hideTrigger = false,
}: TurnCapabilityToggleProps) {
  const t = useTranslations('chat.turnCapabilities');
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;
  const setOpen = useCallback(
    (nextOpen: boolean) => {
      if (isControlled) {
        controlledOnOpenChange?.(nextOpen);
      } else {
        setUncontrolledOpen(nextOpen);
      }
    },
    [controlledOnOpenChange, isControlled],
  );

  const { actionMode, agentConfig } = useChatStore(
    useShallow((state) => ({
      actionMode: state.actionMode,
      agentConfig: state.agentConfig,
    })),
  );
  const { marketSkills, localSkills } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
    })),
  );
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);

  const skillOptions = useMemo<CapabilityOption[]>(() => {
    const configuredSkillIds = agentConfig?.selectedSkillIds ?? [];
    if (configuredSkillIds.length === 0) {
      return [];
    }
    const byId = new Map(
      [...marketSkills, ...localSkills]
        .filter((skill) => skill.user_invocable !== false)
        .map((skill) => [skill.id, skill.name] as const),
    );
    return configuredSkillIds.flatMap((skillId) => {
      const name = byId.get(skillId);
      return name ? [{ id: skillId, label: name }] : [];
    });
  }, [agentConfig?.selectedSkillIds, localSkills, marketSkills]);

  const mcpOptions = useMemo<CapabilityOption[]>(() => {
    const configuredMcpNames = agentConfig?.selectedMcpNames ?? [];
    if (configuredMcpNames.length === 0) {
      return [];
    }
    const normalized = normalizeMCPServiceConfigs(mcpConfigs);
    const byName = new Map(normalized.map((config) => [config.name, config.name] as const));
    return configuredMcpNames.flatMap((name) => {
      const mcpName = byName.get(name);
      return mcpName ? [{ id: mcpName, label: mcpName }] : [];
    });
  }, [agentConfig?.selectedMcpNames, mcpConfigs]);

  const baseSkillIds = useMemo(() => skillOptions.map((option) => option.id), [skillOptions]);
  const baseMcpNames = useMemo(() => mcpOptions.map((option) => option.id), [mcpOptions]);

  const activeSkillIds = useMemo(
    () => resolveEffectiveTurnSelection(baseSkillIds, selection?.skillIds ?? null),
    [baseSkillIds, selection?.skillIds],
  );
  const activeMcpNames = useMemo(
    () => resolveEffectiveTurnSelection(baseMcpNames, selection?.mcpNames ?? null),
    [baseMcpNames, selection?.mcpNames],
  );

  const activeSkillSet = useMemo(() => new Set(activeSkillIds), [activeSkillIds]);
  const activeMcpSet = useMemo(() => new Set(activeMcpNames), [activeMcpNames]);

  const hasOverride = selection !== null;

  const applySelection = useCallback(
    (nextSkillIds: string[] | null, nextMcpNames: string[] | null) => {
      const normalized = normalizeTurnCapabilitySelection(baseSkillIds, baseMcpNames, nextSkillIds, nextMcpNames);
      onSelectionChange(normalized);
    },
    [baseMcpNames, baseSkillIds, onSelectionChange],
  );

  const toggleSkill = useCallback(
    (skillId: string) => {
      const nextSkills = activeSkillSet.has(skillId)
        ? activeSkillIds.filter((id) => id !== skillId)
        : [...activeSkillIds, skillId];
      applySelection(nextSkills, selection?.mcpNames ?? null);
    },
    [activeSkillIds, activeSkillSet, applySelection, selection?.mcpNames],
  );

  const toggleMcp = useCallback(
    (mcpName: string) => {
      const nextMcps = activeMcpSet.has(mcpName)
        ? activeMcpNames.filter((name) => name !== mcpName)
        : [...activeMcpNames, mcpName];
      applySelection(selection?.skillIds ?? null, nextMcps);
    },
    [activeMcpNames, activeMcpSet, applySelection, selection?.skillIds],
  );

  const clearOverride = useCallback(() => {
    onSelectionChange(null);
  }, [onSelectionChange]);

  if (actionMode !== 'agent' || (baseSkillIds.length === 0 && baseMcpNames.length === 0)) {
    return null;
  }

  const totalActiveCount = activeSkillIds.length + activeMcpNames.length;

  return (
    <TooltipProvider delayDuration={300}>
      <Popover open={open} onOpenChange={setOpen}>
        {hideTrigger ? (
          <PopoverTrigger asChild>
            <span className="sr-only" aria-hidden="true" />
          </PopoverTrigger>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  disabled={disabled}
                  className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors disabled:opacity-50',
                    hasOverride
                      ? 'bg-primary/10 text-primary hover:bg-primary/20'
                      : 'text-muted-foreground/70 hover:text-muted-foreground hover:bg-muted/50',
                  )}
                >
                  <SlidersHorizontal size={14} />
                  {hasOverride && <span className="font-medium">{totalActiveCount}</span>}
                </button>
              </PopoverTrigger>
            </TooltipTrigger>
            <TooltipContent side="top">
              <p>
                {hasOverride
                  ? t('activeCount', { skills: activeSkillIds.length, mcps: activeMcpNames.length })
                  : t('tooltip')}
              </p>
            </TooltipContent>
          </Tooltip>
        )}

        <PopoverContent className="w-72 max-w-[calc(100vw-2rem)] p-0" side="top" align="start" sideOffset={8}>
          <div className="px-3 py-2.5 border-b border-border/50 flex items-center justify-between">
            <span className="text-sm font-medium">{t('popoverTitle')}</span>
            {hasOverride && (
              <button
                type="button"
                onClick={clearOverride}
                disabled={disabled}
                className="text-xs text-primary hover:underline disabled:opacity-50"
              >
                {t('clearOverride')}
              </button>
            )}
          </div>

          <div className="max-h-[280px] overflow-y-auto py-1">
            <div className="px-3 py-1 text-[11px] uppercase tracking-wide text-muted-foreground/70">
              {t('skillsSection')}
            </div>
            {skillOptions.length > 0 ? (
              skillOptions.map((skill) => (
                <CapabilityRow
                  key={skill.id}
                  label={skill.label}
                  active={activeSkillSet.has(skill.id)}
                  onClick={() => toggleSkill(skill.id)}
                  disabled={disabled}
                />
              ))
            ) : (
              <div className="px-3 py-1.5 text-xs text-muted-foreground">{t('noSkills')}</div>
            )}

            <div className="mt-1 border-t border-border/40 px-3 py-1 text-[11px] uppercase tracking-wide text-muted-foreground/70">
              {t('mcpSection')}
            </div>
            {mcpOptions.length > 0 ? (
              mcpOptions.map((mcp) => (
                <CapabilityRow
                  key={mcp.id}
                  label={mcp.label}
                  active={activeMcpSet.has(mcp.id)}
                  onClick={() => toggleMcp(mcp.id)}
                  disabled={disabled}
                />
              ))
            ) : (
              <div className="px-3 py-1.5 text-xs text-muted-foreground">{t('noMcp')}</div>
            )}
          </div>

          <div className="px-3 py-2 border-t border-border/50">
            <span className="text-xs text-muted-foreground">
              {hasOverride ? t('nextTurnOnly') : t('usingAgentDefaults')}
            </span>
          </div>
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
}

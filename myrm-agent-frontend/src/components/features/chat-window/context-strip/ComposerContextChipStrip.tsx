'use client';

/**
 * [INPUT]
 * - ContextChipItem: 原子上下文胶囊
 * - ActiveCapabilityBadge: 负载与 Amber Nudge 指示器
 * - TurnCapabilityToggle: 单轮能力范围调整 popover
 * - useChatStore, useSkillStore, useConfigStore: 响应式状态源
 *
 * [OUTPUT]
 * - ComposerContextChipStrip: 聊天输入区上方统一内联上下文胶囊条。
 *   优雅聚合技能激活、工作流模板、单轮能力范围、附件与负载预警，提供单行自适应流与折叠支持。
 *
 * [POS]
 * 输入区上方唯一上下文挂载指示中枢。
 */

import * as React from 'react';
import { Sparkles, Workflow, SlidersHorizontal, MoreHorizontal } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { cn } from '@/lib/utils/classnameUtils';
import { formatSkillChipLabel } from '@/lib/utils/messageUtils';
import { normalizeMCPServiceConfigs } from '@/lib/utils/mcpConfigNormalizer';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';
import useChatStore from '@/store/useChatStore';
import useSkillStore from '@/store/skill/useSkillStore';
import useConfigStore from '@/store/useConfigStore';
import { ContextChipItem } from './ContextChipItem';
import { ActiveCapabilityBadge } from './ActiveCapabilityBadge';
import TurnCapabilityToggle from '@/components/features/message-input-actions/TurnCapabilityToggle';

export interface ComposerContextChipStripProps {
  turnCapabilitySelection: TurnCapabilitySelection | null;
  onTurnCapabilityChange: (selection: TurnCapabilitySelection | null) => void;
  disabled?: boolean;
  className?: string;
  maxVisibleChips?: number;
}

const OVERLOAD_TOOL_COUNT_THRESHOLD = 15;

export function ComposerContextChipStrip({
  turnCapabilitySelection,
  onTurnCapabilityChange,
  disabled = false,
  className,
  maxVisibleChips = 4,
}: ComposerContextChipStripProps) {
  const t = useTranslations('chat.contextStrip');
  const turnT = useTranslations('chat.turnCapabilities');
  const workflowT = useTranslations('chat.workflowTemplateArmed');

  const [isCapabilityPopoverOpen, setIsCapabilityPopoverOpen] = React.useState(false);

  // 订阅 ChatStore 中的技能与模板状态
  const {
    pendingExplicitSkillActivation,
    setPendingExplicitSkillActivation,
    pendingWorkflowTemplateId,
    pendingWorkflowTemplateDisplayName,
    clearPendingWorkflowTemplate,
    setIsWorkflowMode,
  } = useChatStore(
    useShallow((s) => ({
      pendingExplicitSkillActivation: s.pendingExplicitSkillActivation,
      setPendingExplicitSkillActivation: s.setPendingExplicitSkillActivation,
      pendingWorkflowTemplateId: s.pendingWorkflowTemplateId,
      pendingWorkflowTemplateDisplayName: s.pendingWorkflowTemplateDisplayName,
      clearPendingWorkflowTemplate: s.clearPendingWorkflowTemplate,
      setIsWorkflowMode: s.setIsWorkflowMode,
    })),
  );

  // 订阅活跃技能与 MCP 列表用于计算负载
  const { availableSkills } = useSkillStore(useShallow((s) => ({ availableSkills: s.skills })));
  const { mcpConfigs } = useConfigStore(useShallow((s) => ({ mcpConfigs: s.mcpConfigs })));

  const normalizedMcp = React.useMemo(() => normalizeMCPServiceConfigs(mcpConfigs), [mcpConfigs]);
  const totalSkillsCount = availableSkills?.length ?? 0;
  const totalMcpCount = normalizedMcp?.length ?? 0;

  // 计算本轮实际生效的技能与 MCP 数量
  const effectiveSkillCount = React.useMemo(() => {
    if (turnCapabilitySelection?.skillIds !== null && turnCapabilitySelection?.skillIds !== undefined) {
      return turnCapabilitySelection.skillIds.length;
    }
    return totalSkillsCount;
  }, [turnCapabilitySelection, totalSkillsCount]);

  const effectiveMcpCount = React.useMemo(() => {
    if (turnCapabilitySelection?.mcpNames !== null && turnCapabilitySelection?.mcpNames !== undefined) {
      return turnCapabilitySelection.mcpNames.length;
    }
    return totalMcpCount;
  }, [turnCapabilitySelection, totalMcpCount]);

  const isOverloaded = effectiveSkillCount + effectiveMcpCount >= OVERLOAD_TOOL_COUNT_THRESHOLD;

  // 收集所有要呈现的胶囊项
  const chips: React.ReactNode[] = [];

  // 1. 工作流模板胶囊
  if (pendingWorkflowTemplateId) {
    const templateLabel = pendingWorkflowTemplateDisplayName?.trim() || pendingWorkflowTemplateId;
    chips.push(
      <ContextChipItem
        key="workflow-template"
        id="workflow-template"
        variant="template"
        icon={<Workflow className="h-3.5 w-3.5" />}
        label={templateLabel}
        subtitle={workflowT('label')}
        disabled={disabled}
        removeAriaLabel={workflowT('disarm')}
        onRemove={() => {
          clearPendingWorkflowTemplate();
          setIsWorkflowMode(false);
        }}
      />,
    );
  }

  // 2. 单轮显式技能激活胶囊 (支持多技能逐项渲染与单项解绑)
  if (pendingExplicitSkillActivation && pendingExplicitSkillActivation.skillNames.length > 0) {
    const { skillNames, instruction } = pendingExplicitSkillActivation;
    skillNames.forEach((name) => {
      chips.push(
        <ContextChipItem
          key={`skill-${name}`}
          id={`skill-${name}`}
          variant="skill"
          icon={<Sparkles className="h-3.5 w-3.5" />}
          label={formatSkillChipLabel(name)}
          subtitle={instruction ?? undefined}
          disabled={disabled}
          removeAriaLabel={t('removeSkill')}
          onRemove={() => {
            const remaining = skillNames.filter((n) => n !== name);
            if (remaining.length === 0) {
              setPendingExplicitSkillActivation(null);
            } else {
              setPendingExplicitSkillActivation({
                ...pendingExplicitSkillActivation,
                skillNames: remaining,
              });
            }
          }}
        />,
      );
    });
  }

  // 3. 单轮能力范围覆写胶囊
  if (turnCapabilitySelection !== null) {
    const parts: string[] = [];
    if (turnCapabilitySelection.skillIds !== null) {
      parts.push(turnT('overrideSkillsShort', { skills: turnCapabilitySelection.skillIds.length }));
    }
    if (turnCapabilitySelection.mcpNames !== null) {
      parts.push(turnT('overrideMcpShort', { mcps: turnCapabilitySelection.mcpNames.length }));
    }
    const summary = parts.join(' · ') || turnT('triggerAria');

    chips.push(
      <ContextChipItem
        key="turn-capability"
        id="turn-capability"
        variant="capability"
        icon={<SlidersHorizontal className="h-3.5 w-3.5" />}
        label={summary}
        disabled={disabled}
        onClick={() => setIsCapabilityPopoverOpen(true)}
        removeAriaLabel={turnT('resetAria')}
        onRemove={() => onTurnCapabilityChange(null)}
      />,
    );
  }

  // 无任何活跃胶囊且未超载时，不占用纵向空间
  if (chips.length === 0 && !isOverloaded) {
    return (
      <TurnCapabilityToggle
        selection={turnCapabilitySelection}
        onSelectionChange={onTurnCapabilityChange}
        disabled={disabled}
        open={isCapabilityPopoverOpen}
        onOpenChange={setIsCapabilityPopoverOpen}
        hideTrigger
      />
    );
  }

  const visibleChips = chips.slice(0, maxVisibleChips);
  const overflowChips = chips.slice(maxVisibleChips);

  return (
    <div
      data-testid="composer-context-chip-strip"
      className={cn(
        'mb-2 flex flex-wrap items-center justify-between gap-1.5 rounded-lg border border-border/40 bg-muted/20 px-2.5 py-1.5 transition-all text-xs',
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5 flex-1 min-w-0">
        {visibleChips}

        {overflowChips.length > 0 ? (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                data-testid="context-chip-overflow"
                className="inline-flex h-6.5 items-center gap-1 rounded-md border border-border/60 bg-muted/60 px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                aria-label={t('moreChipsAria', { count: overflowChips.length })}
              >
                <MoreHorizontal className="h-3 w-3" />
                <span>+{overflowChips.length}</span>
              </button>
            </PopoverTrigger>
            <PopoverContent side="top" align="start" className="flex flex-col gap-1.5 p-2 w-auto max-w-sm">
              <span className="text-[11px] font-medium text-muted-foreground px-1">{t('moreContextTitle')}</span>
              <div className="flex flex-wrap gap-1.5">{overflowChips}</div>
            </PopoverContent>
          </Popover>
        ) : null}
      </div>

      <div className="shrink-0 ml-auto pl-1">
        <ActiveCapabilityBadge
          skillCount={effectiveSkillCount}
          mcpCount={effectiveMcpCount}
          isOverloaded={isOverloaded}
          onClick={() => setIsCapabilityPopoverOpen(true)}
        />
      </div>

      {/* 隐藏式触发的单轮能力范围 Popover 控制器 */}
      <TurnCapabilityToggle
        selection={turnCapabilitySelection}
        onSelectionChange={onTurnCapabilityChange}
        disabled={disabled}
        open={isCapabilityPopoverOpen}
        onOpenChange={setIsCapabilityPopoverOpen}
        hideTrigger
      />
    </div>
  );
}

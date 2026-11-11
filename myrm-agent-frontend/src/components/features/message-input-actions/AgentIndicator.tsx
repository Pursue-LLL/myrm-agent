'use client';

/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * @/store/useAgentStore::useAgentStore (POS: 智能体数据中心)
 * @/hooks/agent/useAgentGallery::useAgentGallery (POS: 智能体画廊与环境可用性逻辑)
 * @/lib/utils/agent-config::buildAgentConfig (POS: 智能体配置映射)
 * ./AgentIndicatorAvatar::AgentIndicatorAvatar (POS: 按钮里的智能体头像)
 *
 * [OUTPUT]
 * AgentIndicator: 输入框选项区的智能体指示器与内联快切下拉组件。
 *
 * [POS]
 * 输入区选项区（「能力」组）与手机操作表里的核心操作项。默认展示当前活跃 Agent 头像/图标与名称；
 * 点击弹出轻量 DropdownMenu，支持在活跃多轮会话中 1 秒热切内置预设（Presets）与自定义智能体（Custom Agents），
 * 联动底层 agentId、skills、MCP、systemPrompt 与安全预设，底部保留详细配置面板与管理中心入口。
 * 菜单项被选中后由下拉自己关闭；每次切换先读取智能体详情，较早发起却较晚完成的切换不会覆盖较新的选择。
 */

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useRef } from 'react';
import { AiNetworkIcon, ArrowDown01Icon, BotIcon } from 'hugeicons-react';
import { Check, SlidersHorizontal, Settings } from 'lucide-react';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import { useShallow } from 'zustand/react/shallow';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { findLucideIcon } from '@/components/agent/lucide-icon-resolver';
import { useAgentGallery } from '@/hooks/agent/useAgentGallery';
import { buildAgentConfig } from '@/lib/utils/agent-config';
import type { PresetAgent } from '@/types/presetAgent';
import type { AgentListItem } from '@/services/agent';
import { toast } from '@/hooks/shared/useToast';
import { AgentIndicatorAvatar } from './AgentIndicatorAvatar';

const MAX_NAME_CHARS = 5;

/**
 * Agent 指示器与快切下拉组件
 * 位于 Composer 输入框的选项区（手机上在操作表里）：
 * 1. 默认展示当前激活智能体头像/图标与名称
 * 2. 点击弹出轻量 DropdownMenu 快速切换已保存智能体或内置预设
 * 3. 底部保留「详细配置与微调」与「管理智能体中心」入口
 */
const AgentIndicator = () => {
  const t = useTranslations('agent.indicator');
  const locale = useLocale();
  const router = useRouter();
  const latestChoice = useRef(0);

  const { agentConfig, setAgentConfig, actionMode, toggleConfigPanel, loading } = useChatStore(
    useShallow((state) => ({
      agentConfig: state.agentConfig,
      setAgentConfig: state.setAgentConfig,
      actionMode: state.actionMode,
      toggleConfigPanel: state.toggleConfigPanel,
      loading: state.loading,
    })),
  );

  // 快速切换预设智能体
  const handleSelectPreset = useCallback(
    async (preset: PresetAgent) => {
      const choice = ++latestChoice.current;
      const fullAgent = await useAgentStore.getState().fetchAgent(preset.id);
      if (choice !== latestChoice.current) {
        return;
      }

      const presetIdentity = { presetId: preset.id, presetName: preset.name, presetIcon: preset.icon };
      setAgentConfig(
        fullAgent
          ? { ...buildAgentConfig(fullAgent), ...presetIdentity }
          : {
              agentId: preset.id,
              selectedSkillIds: preset.skillIds || [],
              skillConfigs: {},
              selectedMcpNames: [],
              systemPrompt: preset.systemPrompt || '',
              useGlobalInstruction: true,
              autoRestoreDomains: [],
              ...presetIdentity,
            },
      );
      toast({ title: t('switchSuccess'), description: preset.name });
    },
    [setAgentConfig, t],
  );

  // 快速切换用户自定义智能体
  const handleSelectCustomAgent = useCallback(
    async (agent: AgentListItem) => {
      const choice = ++latestChoice.current;
      const fullAgent = await useAgentStore.getState().fetchAgent(agent.id);
      if (choice !== latestChoice.current) {
        return;
      }

      // The list endpoint omits system_prompt / auto_restore_domains, so fall back to
      // the shared mapper shape rather than fabricating fields the list DTO never carries.
      setAgentConfig(
        fullAgent
          ? buildAgentConfig(fullAgent)
          : {
              agentId: agent.id,
              agentName: agent.name,
              avatarUrl: agent.avatar_url,
              selectedSkillIds: agent.skill_ids ?? [],
              selectedMcpNames: agent.mcp_ids ?? [],
              systemPrompt: '',
              useGlobalInstruction: true,
              skillConfigs: {},
              autoRestoreDomains: [],
            },
      );
      toast({ title: t('switchSuccess'), description: agent.name });
    },
    [setAgentConfig, t],
  );

  const { presetAgents, customAgents, handlePresetClick, handleCustomAgentClick } = useAgentGallery({
    onSelectPreset: handleSelectPreset,
    onSelectCustomAgent: handleSelectCustomAgent,
  });

  const selectedSkillCount = agentConfig?.selectedSkillIds?.length || 0;
  const selectedMcpCount = agentConfig?.selectedMcpNames?.length || 0;
  const hasCustomInstruction = (agentConfig?.systemPrompt?.trim().length || 0) > 0;
  const totalConfigCount = selectedSkillCount + selectedMcpCount + (hasCustomInstruction ? 1 : 0);

  const hasSelectedAgent = !!agentConfig && (!!agentConfig.agentId || !!agentConfig.presetId || totalConfigCount > 0);

  const formatAgentName = (name?: string) => {
    if (!name) {
      return t('default');
    }
    // Count characters rather than UTF-16 units, so the cut never splits an emoji in two.
    const characters = Array.from(name);
    return characters.length > MAX_NAME_CHARS ? `${characters.slice(0, MAX_NAME_CHARS).join('')}...` : name;
  };

  if (actionMode !== 'agent') {
    return null;
  }

  const currentAgentId = agentConfig?.agentId || agentConfig?.presetId;

  return (
    <DropdownMenu>
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild disabled={loading}>
              <button
                type="button"
                className={cn(
                  'inline-flex shrink-0 items-center gap-1.5 rounded-lg whitespace-nowrap',
                  'text-xs font-medium transition-all duration-200',
                  'border cursor-pointer',
                  hasSelectedAgent
                    ? 'px-2 py-1.5 bg-primary/10 border-primary/30 text-primary hover:bg-primary/20'
                    : 'p-1.5 bg-muted/50 border-border hover:bg-muted hover:border-border/80 text-muted-foreground',
                  loading && 'opacity-60 cursor-not-allowed',
                )}
                aria-label={t('switchAgent')}
              >
                <div className="w-5 h-5">
                  <AgentIndicatorAvatar agentConfig={agentConfig} hasSelectedAgent={hasSelectedAgent} />
                </div>

                {hasSelectedAgent && (
                  <span className="hidden xl:inline">
                    {formatAgentName(
                      agentConfig?.presetName ||
                        (agentConfig?.agentId
                          ? getBuiltinAgentName(agentConfig.agentId, agentConfig.agentName || '', locale)
                          : agentConfig?.agentName),
                    )}
                  </span>
                )}

                <ArrowDown01Icon size={12} className="transition-transform duration-200" />
              </button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-[280px] py-2.5 px-3" sideOffset={8}>
            <div className="text-xs text-left text-muted-foreground space-y-1.5">
              <p>{t('tooltipLine1')}</p>
              <p>{t('tooltipLine2')}</p>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-64 max-h-80 overflow-y-auto p-1.5">
        {/* 预置专家 */}
        {presetAgents.length > 0 && (
          <>
            <DropdownMenuLabel className="text-[11px] font-semibold text-muted-foreground px-2 py-1">
              {t('builtinPresets')}
            </DropdownMenuLabel>
            {presetAgents.map((preset) => {
              const isSelected = currentAgentId === preset.id;
              const IconComp = findLucideIcon(preset.icon) ?? BotIcon;

              return (
                <DropdownMenuItem
                  key={preset.id}
                  onClick={() => handlePresetClick(preset)}
                  className={cn(
                    'flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg text-xs cursor-pointer',
                    isSelected && 'bg-primary/10 text-primary font-medium',
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-4 h-4 shrink-0 flex items-center justify-center text-muted-foreground">
                      <IconComp size={14} className={isSelected ? 'text-primary' : ''} />
                    </div>
                    <span className="truncate">{preset.name}</span>
                  </div>
                  {isSelected && <Check size={14} className="text-primary shrink-0" />}
                </DropdownMenuItem>
              );
            })}
          </>
        )}

        {/* 自定义智能体 */}
        {customAgents.length > 0 && (
          <>
            <DropdownMenuSeparator className="my-1.5" />
            <DropdownMenuLabel className="text-[11px] font-semibold text-muted-foreground px-2 py-1">
              {t('customAgents')}
            </DropdownMenuLabel>
            {customAgents.map((agent) => {
              const isSelected = currentAgentId === agent.id;
              return (
                <DropdownMenuItem
                  key={agent.id}
                  onClick={() => handleCustomAgentClick(agent)}
                  className={cn(
                    'flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg text-xs cursor-pointer',
                    isSelected && 'bg-primary/10 text-primary font-medium',
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-4 h-4 shrink-0 rounded bg-primary/20 flex items-center justify-center text-[10px]">
                      <AiNetworkIcon size={12} className="text-primary" />
                    </div>
                    <span className="truncate">{agent.name}</span>
                  </div>
                  {isSelected && <Check size={14} className="text-primary shrink-0" />}
                </DropdownMenuItem>
              );
            })}
          </>
        )}

        <DropdownMenuSeparator className="my-1.5" />

        {/* 详细配置与微调 */}
        <DropdownMenuItem
          onClick={toggleConfigPanel}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs cursor-pointer text-muted-foreground hover:text-foreground"
        >
          <SlidersHorizontal size={14} className="shrink-0" />
          <span>{t('openConfigPanel')}</span>
        </DropdownMenuItem>

        {/* 管理智能体中心 */}
        <DropdownMenuItem
          onClick={() => router.push('/settings/agents')}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs cursor-pointer text-muted-foreground hover:text-foreground"
        >
          <Settings size={14} className="shrink-0" />
          <span>{t('manageAgents')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default AgentIndicator;

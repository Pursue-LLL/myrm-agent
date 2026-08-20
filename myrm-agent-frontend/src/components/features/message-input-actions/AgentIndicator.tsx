'use client';

/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * @/store/useAgentStore::useAgentStore (POS: 智能体数据中心)
 * @/hooks/agent/useAgentGallery::useAgentGallery (POS: 智能体画廊与环境可用性逻辑)
 * @/lib/utils/agentConfigMapper::buildAgentConfig (POS: 智能体配置映射)
 *
 * [OUTPUT]
 * AgentIndicator: 输入框工具栏智能体指示器与内联快切下拉组件。
 *
 * [POS]
 * 输入区工具栏核心操作项。默认展示当前活跃 Agent 头像/图标与名称；
 * 点击弹出轻量 DropdownMenu，支持在活跃多轮会话中 1 秒热切内置预设（Presets）与自定义智能体（Custom Agents），
 * 联动底层 agentId、skills、MCP、systemPrompt 与安全预设，底部保留详细配置面板与管理中心入口。
 */

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';
import { AiNetworkIcon, ArrowDown01Icon, BotIcon } from 'hugeicons-react';
import { Check, SlidersHorizontal, Settings } from 'lucide-react';
import { AgentIcon } from '@/components/agent/agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';
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
import * as LucideIcons from 'lucide-react';
import { useAgentGallery } from '@/hooks/agent/useAgentGallery';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import type { PresetAgent } from '@/types/presetAgent';
import type { AgentListItem } from '@/services/agent';
import { toast } from '@/hooks/shared/useToast';

// 预设头像颜色方案 - 与编辑页保持一致
const avatarGradients = [
  { from: 'from-primary', to: 'to-violet-500' },
  { from: 'from-blue-500', to: 'to-cyan-500' },
  { from: 'from-emerald-500', to: 'to-teal-500' },
  { from: 'from-orange-500', to: 'to-amber-500' },
  { from: 'from-pink-500', to: 'to-rose-500' },
  { from: 'from-indigo-500', to: 'to-purple-500' },
];

const stableGradientIndex = (value: string): number => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return (hash >>> 0) % avatarGradients.length;
};

const getGradientFromAvatarUrl = (avatarUrl?: string, fallbackIndex: number = 0) => {
  if (avatarUrl?.startsWith('gradient:')) {
    const gradientIndex = parseInt(avatarUrl.replace('gradient:', ''), 10);
    if (!isNaN(gradientIndex) && gradientIndex >= 0 && gradientIndex < avatarGradients.length) {
      return avatarGradients[gradientIndex];
    }
  }
  return avatarGradients[fallbackIndex % avatarGradients.length];
};

/**
 * Agent 指示器与快切下拉组件
 * 位于 Composer 输入框工具栏：
 * 1. 默认展示当前激活智能体头像/图标与名称
 * 2. 点击弹出轻量 DropdownMenu 快速切换已保存智能体或内置预设
 * 3. 底部保留「详细配置与微调」与「管理智能体中心」入口
 */
const AgentIndicator = () => {
  const t = useTranslations('agent.indicator');
  const locale = useLocale();
  const router = useRouter();
  const [dropdownOpen, setDropdownOpen] = useState(false);

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
    async (preset: PresetAgent, workingDirectory?: string) => {
      let config = {
        agentId: preset.id,
        selectedSkillIds: preset.skillIds || [],
        skillConfigs: {},
        selectedMcpNames: [],
        systemPrompt: preset.systemPrompt || '',
        useGlobalInstruction: true,
        autoRestoreDomains: [],
        presetId: preset.id,
        presetName: preset.name,
        presetIcon: preset.icon,
      };

      try {
        const fullAgent = await useAgentStore.getState().fetchAgent(preset.id);
        if (fullAgent) {
          config = {
            ...buildAgentConfig(fullAgent),
            presetId: preset.id,
            presetName: preset.name,
            presetIcon: preset.icon,
          };
        }
      } catch (e) {
        console.error('Failed to fetch full agent details for preset', e);
      }

      if (workingDirectory) {
        config.agentDescription = `workingDirectory:${workingDirectory}`;
      }

      setAgentConfig(config);
      setDropdownOpen(false);
      toast({
        title: t('switchSuccess'),
        description: preset.name,
      });
    },
    [setAgentConfig, t],
  );

  // 快速切换用户自定义智能体
  const handleSelectCustomAgent = useCallback(
    async (agent: AgentListItem) => {
      try {
        const fullAgent = await useAgentStore.getState().fetchAgent(agent.id);
        if (fullAgent) {
          setAgentConfig(buildAgentConfig(fullAgent));
        } else {
          setAgentConfig({
            agentId: agent.id,
            agentName: agent.name,
            avatarUrl: agent.avatar_url,
            selectedSkillIds: agent.skill_ids || [],
            selectedMcpNames: agent.mcp_ids || [],
            systemPrompt: agent.system_prompt || '',
            useGlobalInstruction: true,
            autoRestoreDomains: agent.auto_restore_domains || [],
          });
        }
        setDropdownOpen(false);
        toast({
          title: t('switchSuccess'),
          description: agent.name,
        });
      } catch (e) {
        console.error('Failed to fetch custom agent details', e);
      }
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
    return name.length > 5 ? `${name.slice(0, 5)}...` : name;
  };

  if (actionMode !== 'agent') {
    return null;
  }

  const getAgentIconGradient = () => {
    if (agentConfig?.presetId) {
      return avatarGradients[stableGradientIndex(agentConfig.presetId)] || avatarGradients[0];
    }
    if (agentConfig?.avatarUrl?.startsWith('gradient:')) {
      const gradientIndex = parseInt(agentConfig.avatarUrl.replace('gradient:', ''), 10);
      if (!isNaN(gradientIndex) && gradientIndex >= 0 && gradientIndex < avatarGradients.length) {
        return avatarGradients[gradientIndex];
      }
    }
    return avatarGradients[0];
  };

  const iconGradient = getAgentIconGradient();

  const renderAgentAvatar = () => {
    if (agentConfig?.avatarUrl) {
      const parsed = parseAvatarUrl(agentConfig.avatarUrl, agentConfig.agentId);
      if (parsed?.type === 'icon') {
        return <AgentIcon iconId={parsed.iconId} size="sm" className="w-5 h-5" />;
      }
      if (parsed?.type === 'gradient') {
        const gradient = getGradientFromAvatarUrl(agentConfig.avatarUrl);
        return (
          <div
            className={cn(
              'w-full h-full rounded flex items-center justify-center',
              'bg-gradient-to-br',
              gradient.from,
              gradient.to,
            )}
          >
            <AiNetworkIcon size={12} className="text-white" />
          </div>
        );
      }
      if (parsed?.type === 'image') {
        return (
          <img src={parsed.src} alt={agentConfig.agentName || 'Agent'} className="w-full h-full rounded object-cover" />
        );
      }
      if (parsed?.type === 'emoji') {
        return <span className="text-xs">{parsed.emoji}</span>;
      }
    }

    if (agentConfig?.presetIcon) {
      const IconComponent = (
        LucideIcons as unknown as Record<string, React.ComponentType<{ size?: number; className?: string }>>
      )[agentConfig.presetIcon];
      if (IconComponent) {
        return (
          <div
            className={cn(
              'w-full h-full rounded flex items-center justify-center',
              'bg-gradient-to-br',
              hasSelectedAgent ? iconGradient.from : '',
              hasSelectedAgent ? iconGradient.to : '',
              !hasSelectedAgent && 'bg-muted-foreground/20',
            )}
          >
            <IconComponent size={12} className={hasSelectedAgent ? 'text-white' : 'text-muted-foreground'} />
          </div>
        );
      }
    }

    return (
      <div
        className={cn(
          'w-full h-full rounded flex items-center justify-center',
          'bg-gradient-to-br',
          hasSelectedAgent ? iconGradient.from : '',
          hasSelectedAgent ? iconGradient.to : '',
          !hasSelectedAgent && 'bg-muted-foreground/20',
        )}
      >
        <BotIcon size={12} className={hasSelectedAgent ? 'text-white' : 'text-muted-foreground'} />
      </div>
    );
  };

  const currentAgentId = agentConfig?.agentId || agentConfig?.presetId;

  return (
    <DropdownMenu open={dropdownOpen} onOpenChange={setDropdownOpen}>
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
                <div className="w-5 h-5">{renderAgentAvatar()}</div>

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
              const IconComp =
                (LucideIcons as unknown as Record<string, React.ComponentType<{ size?: number; className?: string }>>)[
                  preset.icon
                ] || BotIcon;

              return (
                <DropdownMenuItem
                  key={preset.id}
                  onClick={() => handlePresetClick(preset)}
                  className={cn(
                    'flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-xs cursor-pointer',
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
                    'flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-xs cursor-pointer',
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
          className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs cursor-pointer text-muted-foreground hover:text-foreground"
        >
          <SlidersHorizontal size={14} className="shrink-0" />
          <span>{t('openConfigPanel')}</span>
        </DropdownMenuItem>

        {/* 管理智能体中心 */}
        <DropdownMenuItem
          onClick={() => router.push('/settings/agents')}
          className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs cursor-pointer text-muted-foreground hover:text-foreground"
        >
          <Settings size={14} className="shrink-0" />
          <span>{t('manageAgents')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default AgentIndicator;

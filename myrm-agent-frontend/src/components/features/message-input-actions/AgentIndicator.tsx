'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useLocale } from 'next-intl';
import { AiNetworkIcon, ArrowDown01Icon, ArrowUp01Icon, BotIcon } from 'hugeicons-react';
import { AgentIcon } from '@/components/agent/agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import * as LucideIcons from 'lucide-react';

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

/**
 * 根据 avatar_url 解析颜色
 */
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
 * Agent 指示器组件
 * 显示在输入框旁边，点击可展开/收起配置面板
 * - 通用助手（默认）：只显示图标，不显示名称
 * - 已选中其他智能体时：显示图标和名称
 * - Hover 时显示提示文案
 */
const AgentIndicator = () => {
  const t = useTranslations('agent.indicator');
  const locale = useLocale();

  const { agentConfig, actionMode, isConfigPanelExpanded, toggleConfigPanel } = useChatStore(
    useShallow((state) => ({
      agentConfig: state.agentConfig,
      actionMode: state.actionMode,
      isConfigPanelExpanded: state.isConfigPanelExpanded,
      toggleConfigPanel: state.toggleConfigPanel,
    })),
  );

  // 计算已配置项数量
  const selectedSkillCount = agentConfig?.selectedSkillIds?.length || 0;
  const selectedMcpCount = agentConfig?.selectedMcpNames?.length || 0;
  const hasCustomInstruction = (agentConfig?.systemPrompt?.trim().length || 0) > 0;
  const totalConfigCount = selectedSkillCount + selectedMcpCount + (hasCustomInstruction ? 1 : 0);

  // 判断是否已选中智能体（包括预设智能体和已保存智能体）
  // 只要有配置或选中了智能体，就认为已选中
  const hasSelectedAgent =
    !!agentConfig &&
    (!!agentConfig.agentId || // 已保存的智能体
      !!agentConfig.presetId || // 预设智能体（包括通用助手）
      totalConfigCount > 0); // 或有任何配置

  // 格式化智能体名称（最多5个字）
  const formatAgentName = (name?: string) => {
    if (!name) return t('default');
    return name.length > 5 ? `${name.slice(0, 5)}...` : name;
  };

  // 只在 agent 模式下显示
  if (actionMode !== 'agent') {
    return null;
  }

  // 获取智能体图标的渐变色（from 和 to 类名）
  const getAgentIconGradient = () => {
    // 1. 预设智能体：根据 presetIcon 的类型或名称匹配一种基础色，或默认色
    if (agentConfig?.presetId) {
      return avatarGradients[stableGradientIndex(agentConfig.presetId)] || avatarGradients[0];
    }

    // 2. 已保存智能体：从 avatarUrl 解析渐变索引
    if (agentConfig?.avatarUrl?.startsWith('gradient:')) {
      const gradientIndex = parseInt(agentConfig.avatarUrl.replace('gradient:', ''), 10);
      if (!isNaN(gradientIndex) && gradientIndex >= 0 && gradientIndex < avatarGradients.length) {
        return avatarGradients[gradientIndex];
      }
    }

    // 3. 默认使用 primary 配色（索引 0）
    return avatarGradients[0];
  };

  const iconGradient = getAgentIconGradient();

  // 渲染智能体头像
  const renderAgentAvatar = () => {
    // 1. 已保存的智能体：使用 avatarUrl
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

    // 2. 预设智能体：使用 presetIcon（Lucide icon 名称）
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

    // 3. 默认：Bot 图标
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

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={toggleConfigPanel}
            className={cn(
              'inline-flex shrink-0 items-center gap-1.5 rounded-lg whitespace-nowrap',
              'text-xs font-medium transition-all duration-200',
              'border cursor-pointer',
              // 按钮样式保持统一的 primary 色系
              hasSelectedAgent
                ? 'px-2 py-1.5 bg-primary/10 border-primary/30 text-primary hover:bg-primary/20'
                : 'p-1.5 bg-muted/50 border-border hover:bg-muted hover:border-border/80 text-muted-foreground',
            )}
            aria-expanded={isConfigPanelExpanded}
            aria-label={isConfigPanelExpanded ? t('collapse') : t('expand')}
          >
            {/* Agent 图标 - 显示智能体头像 */}
            <div className="w-5 h-5">{renderAgentAvatar()}</div>

            {/* 名称 - 只在选中智能体时显示 */}
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

            {/* 展开/收起箭头 - 始终显示 */}
            {isConfigPanelExpanded ? (
              <ArrowUp01Icon size={12} className="transition-transform duration-200" />
            ) : (
              <ArrowDown01Icon size={12} className="transition-transform duration-200" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[280px] py-2.5 px-3" sideOffset={8}>
          <div className="text-xs text-left text-muted-foreground space-y-1.5">
            <p>{t('tooltipLine1')}</p>
            <p>{t('tooltipLine2')}</p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default AgentIndicator;

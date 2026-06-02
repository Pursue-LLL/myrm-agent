import { useState, useRef, useCallback, useMemo, memo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { AgentListItem, Agent } from '@/services/agent';
import { cn } from '@/lib/utils/classnameUtils';
import { ChevronRight, Wand2, Plug, FileText, Wrench, Loader2, Check } from 'lucide-react';
import { AiNetworkIcon } from 'hugeicons-react';
import { AgentIcon } from '@/components/agent/agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { brickOffsets } from './agentGalleryConstants';
import { getGradientFromAvatarUrl } from '@/utils/agentGalleryUtils';

// 配置名称映射类型
export interface ConfigNameMaps {
  skills: Map<string, string>;
  mcps: Map<string, string>;
}

interface AgentBrickCardProps {
  agent: AgentListItem;
  index: number;
  onClick: () => void;
  onLoadDetails: (agentId: string) => Promise<Agent | null>;
  cachedDetails?: Agent;
  configNameMaps: ConfigNameMaps;
  isSelected?: boolean;
}

/**
 * 砖墙智能体卡片 - 大卡片带描述，错落排布
 * 悬停时显示配置详情
 */
const AgentBrickCard = ({
  agent,
  index,
  onClick,
  onLoadDetails,
  cachedDetails,
  configNameMaps,
  isSelected,
}: AgentBrickCardProps) => {
  const t = useTranslations('agent.configPanel');
  const locale = useLocale();
  const gradient = getGradientFromAvatarUrl(agent.avatar_url, index);
  const parsed = parseAvatarUrl(agent.avatar_url, agent.id);
  const displayName = getBuiltinAgentName(agent.id, agent.name, locale);
  const displayDesc = getBuiltinAgentDescription(agent.id, agent.description || '', locale);

  // 本地加载状态
  const [isLoading, setIsLoading] = useState(false);
  const [details, setDetails] = useState<Agent | null>(cachedDetails || null);
  const hasLoadedRef = useRef(false);

  // 获取错落偏移量
  const offset = brickOffsets[index % brickOffsets.length];

  // 随机确定卡片大小 - 部分卡片更大
  const isLargeCard = useMemo(() => {
    const hasLongDesc = agent.description && agent.description.length > 30;
    return index % 3 === 0 || hasLongDesc;
  }, [index, agent.description]);

  // 悬停时加载详情
  const handleHoverStart = useCallback(async () => {
    if (hasLoadedRef.current || cachedDetails) {
      setDetails(cachedDetails || details);
      return;
    }

    setIsLoading(true);
    const loadedDetails = await onLoadDetails(agent.id);
    setDetails(loadedDetails);
    setIsLoading(false);
    hasLoadedRef.current = true;
  }, [agent.id, onLoadDetails, cachedDetails, details]);

  // 获取配置详情名称列表
  const configDetails = useMemo(() => {
    if (!details) return null;

    // 获取技能名称列表
    const skillNames = (details.skill_ids || [])
      .map((id) => configNameMaps.skills.get(id))
      .filter((name): name is string => !!name);

    // 获取 MCP 名称列表（mcp_ids 存储的是 name）
    const mcpNames = (details.mcp_ids || [])
      .map((name) => configNameMaps.mcps.get(name) || name)
      .filter((name): name is string => !!name);

    const builtinToolNames = (details.enabled_builtin_tools || [])
      .map((id) => t(`builtinToolNames.${id}`))
      .filter(Boolean);

    // 系统指令（截取前50字符）
    const promptPreview = details.system_prompt?.trim()
      ? details.system_prompt.trim().slice(0, 50) + (details.system_prompt.trim().length > 50 ? '...' : '')
      : null;

    return {
      skillNames,
      mcpNames,
      builtinToolNames,
      promptPreview,
    };
  }, [details, configNameMaps, t]);

  const cardContent = (
    <button
      onClick={onClick}
      className={cn(
        'group relative flex flex-col',
        'p-3 rounded-xl shrink-0',
        // 移动端使用网格自适应，PC端使用固定宽度
        'w-full lg:w-auto',
        isLargeCard ? 'lg:w-[180px]' : 'lg:w-[150px]',
        'backdrop-blur-lg',
        'transition-all duration-300 ease-out',
        'cursor-pointer text-left',
        'bg-white/50 dark:bg-white/[0.07]',
        'border border-white/60 dark:border-white/10',
        'hover:bg-white/70 dark:hover:bg-white/[0.12]',
        'hover:border-primary/30',
        'hover:shadow-xl hover:shadow-primary/5 dark:hover:shadow-primary/10',
        'hover:scale-[1.03] hover:-rotate-0',
        // PC端应用砖墙偏移效果
        'brick-card',
      )}
      style={
        {
          '--brick-translate-y': `${offset.translateY}px`,
          '--brick-rotate': `${offset.rotate}deg`,
        } as React.CSSProperties
      }
    >
      {/* 选中态激活标记 - 右上角，轻量描边风格 */}
      {isSelected && (
        <div className="absolute -top-1 -right-1 z-10">
          <div className="w-4 h-4 rounded-full border-2 border-primary bg-background flex items-center justify-center">
            <Check size={10} className="text-primary" strokeWidth={2.5} />
          </div>
        </div>
      )}

      {/* 顶部：头像 + 名称 */}
      <div className="flex items-center gap-2.5 mb-2">
        <div
          className={cn(
            'w-10 h-10 rounded-lg flex items-center justify-center shrink-0',
            'bg-gradient-to-br shadow-md',
            gradient.from,
            gradient.to,
            'group-hover:scale-110 group-hover:shadow-lg',
            'transition-all duration-300',
          )}
        >
          {parsed?.type === 'icon' ? (
            <AgentIcon iconId={parsed.iconId} size="md" className="w-10 h-10" />
          ) : parsed?.type === 'image' ? (
            <img src={parsed.src} alt={agent.name} className="w-full h-full rounded-lg object-cover" />
          ) : parsed?.type === 'emoji' ? (
            <span className="text-lg">{parsed.emoji}</span>
          ) : (
            <AiNetworkIcon size={18} className="text-white drop-" />
          )}
        </div>
        <div className="flex-1 min-w-0 flex items-center gap-1.5">
          <h4
            className={cn(
              'text-sm font-semibold truncate',
              'text-foreground/90 group-hover:text-foreground',
              'transition-colors duration-200',
            )}
          >
            {displayName}
          </h4>
          {agent.agent_type === 'team' && (
            <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded-full bg-primary/10 text-primary border border-primary/20">
              {t('teamBadge')}
            </span>
          )}
        </div>
      </div>

      {/* 描述 */}
      <p
        className={cn(
          'text-xs text-muted-foreground/80 leading-relaxed',
          'line-clamp-2 min-h-[2.5em]',
          'group-hover:text-muted-foreground',
          'transition-colors duration-200',
        )}
      >
        {displayDesc || t('noDescription')}
      </p>

      {/* 使用提示 - 底部（选中态不显示） */}
      {!isSelected && (
        <div
          className={cn(
            'mt-2 pt-2 border-t border-border/30',
            'flex items-center justify-between',
            'transition-opacity duration-200',
          )}
        >
          <span className="text-xs font-medium text-primary group-hover:text-primary/90">{t('useAgent')}</span>
          <ChevronRight
            size={12}
            className={cn(
              'text-primary group-hover:text-primary/90',
              'group-hover:translate-x-0.5',
              'transition-all duration-200',
            )}
          />
        </div>
      )}
    </button>
  );

  return (
    <HoverCard openDelay={300} closeDelay={100} onOpenChange={(open) => open && handleHoverStart()}>
      <HoverCardTrigger asChild>{cardContent}</HoverCardTrigger>
      <HoverCardContent className="w-64 p-3" side="top" align="center" sideOffset={8}>
        <div className="space-y-3">
          {/* 标题 */}
          <div className="flex items-center gap-2 pb-2 border-b border-border/50">
            <div
              className={cn(
                'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                'bg-gradient-to-br',
                gradient.from,
                gradient.to,
              )}
            >
              <AiNetworkIcon size={14} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <h5 className="text-sm font-semibold truncate">{displayName}</h5>
              <p className="text-[10px] text-muted-foreground">{t('configDetails')}</p>
            </div>
          </div>

          {/* 配置详情 - 只展示已配置的项目，显示具体名称 */}
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={20} className="animate-spin text-muted-foreground" />
            </div>
          ) : configDetails ? (
            (() => {
              const hasAnyConfig =
                configDetails.skillNames.length > 0 ||
                configDetails.mcpNames.length > 0 ||
                configDetails.builtinToolNames.length > 0 ||
                configDetails.promptPreview;

              if (!hasAnyConfig) {
                return <p className="text-xs text-muted-foreground text-center py-2">{t('noConfiguredItems')}</p>;
              }

              return (
                <div className="space-y-2">
                  {/* 技能 - 仅在已配置时显示 */}
                  {configDetails.skillNames.length > 0 && (
                    <div className="flex gap-2 p-2 rounded-lg bg-primary/10">
                      <Wand2 size={14} className="text-primary shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] text-muted-foreground mb-0.5">{t('skill')}</p>
                        <p className="text-xs text-foreground leading-relaxed">{configDetails.skillNames.join('、')}</p>
                      </div>
                    </div>
                  )}

                  {/* MCP - 仅在已配置时显示 */}
                  {configDetails.mcpNames.length > 0 && (
                    <div className="flex gap-2 p-2 rounded-lg bg-primary/10">
                      <Plug size={14} className="text-primary shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] text-muted-foreground mb-0.5">MCP</p>
                        <p className="text-xs text-foreground leading-relaxed">{configDetails.mcpNames.join('、')}</p>
                      </div>
                    </div>
                  )}

                  {/* 内置工具 - 仅在已配置时显示 */}
                  {configDetails.builtinToolNames.length > 0 && (
                    <div className="flex gap-2 p-2 rounded-lg bg-primary/10">
                      <Wrench size={14} className="text-primary shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] text-muted-foreground mb-0.5">{t('builtinTools')}</p>
                        <p className="text-xs text-foreground leading-relaxed">
                          {configDetails.builtinToolNames.join('、')}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* 指令 - 仅在已配置时显示预览 */}
                  {configDetails.promptPreview && (
                    <div className="flex gap-2 p-2 rounded-lg bg-primary/10">
                      <FileText size={14} className="text-primary shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] text-muted-foreground mb-0.5">{t('instruction')}</p>
                        <p className="text-xs text-foreground leading-relaxed line-clamp-2">
                          {configDetails.promptPreview}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()
          ) : (
            <p className="text-xs text-muted-foreground text-center py-2">{t('loadFailed')}</p>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
};

export default memo(AgentBrickCard);

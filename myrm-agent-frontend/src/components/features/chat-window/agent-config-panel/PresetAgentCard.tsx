/**
 * 预置智能体卡片组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - @/types/presetAgent::PresetAgent (POS: 预置智能体类型定义)
 * - ./constants::iconMap, categoryColors (POS: 图标和颜色常量)
 * - ./CLIWorkingDirectory (POS: CLI 智能体工作路径管理组件)
 *
 * [OUTPUT]
 * - PresetAgentCard: 预置智能体卡片组件
 *   - 显示智能体图标、名称、描述
 *   - 显示示例案例（quickTasks）
 *   - CLI 智能体显示工作路径配置
 *
 * [POS]
 * 预置智能体卡片。在智能体画廊中展示单个预置智能体，
 * 支持选择和配置。CLI 智能体使用 CLIWorkingDirectory 子组件
 * 管理工作路径。扁平化设计，无展开收起，信息一目了然。
 */

import { useCallback, memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertCircle, Check, FileText } from 'lucide-react';
import type { PresetAgent } from '@/types/presetAgent';
import { iconMap, categoryColors } from './constants';
import CLIWorkingDirectory from './CLIWorkingDirectory';

interface PresetAgentCardProps {
  agent: PresetAgent & { isAvailable?: boolean };
  isSelected: boolean;
  onSelect: (agent: PresetAgent) => void;
  /** CLI 智能体的工作目录 */
  workingDirectory?: string;
  /** 工作目录变更回调 */
  onWorkingDirectoryChange?: (directory: string) => void;
  /** 用于震动动画的 ref */
  cardRef?: React.RefObject<HTMLDivElement | null>;
}

const isCLIVisualAgent = (agent: PresetAgent) => {
  return agent.category === 'cli_visual' && agent.requiresWorkingDirectory === true;
};

/**
 * 预置智能体卡片 - 扁平化设计，无展开收起
 * 包含：Logo、名称、描述、示例案例、启用状态
 * CLI 智能体使用 CLIWorkingDirectory 子组件
 */
const PresetAgentCard = ({
  agent,
  isSelected,
  onSelect,
  workingDirectory,
  onWorkingDirectoryChange,
  cardRef,
}: PresetAgentCardProps) => {
  const t = useTranslations('presetAgent');
  const tPanel = useTranslations('agentConfigPanel');
  const IconComponent = iconMap[agent.icon] || iconMap.MessageCircle;
  const colors = categoryColors[agent.category] || categoryColors['general'];
  const isCLI = isCLIVisualAgent(agent);

  // 处理卡片点击
  const handleCardClick = useCallback(() => {
    onSelect(agent);
  }, [agent, onSelect]);

  // 处理卡片键盘事件（可访问性）
  const handleCardKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(agent);
      }
    },
    [agent, onSelect],
  );

  return (
    <div ref={cardRef} className="relative">
      {/* 选中态 - 右上角状态图标 */}
      {isSelected && (
        <div className="absolute top-3 right-3 z-20">
          <div className="w-6 h-6 rounded-full bg-primary/30 backdrop-blur-sm flex items-center justify-center shadow-md shadow-primary/20 ring-1 ring-white/50">
            <Check size={14} className="text-white" strokeWidth={2.5} />
          </div>
        </div>
      )}
      <div
        role="button"
        tabIndex={0}
        onClick={handleCardClick}
        onKeyDown={handleCardKeyDown}
        className={cn(
          'group relative w-full text-left cursor-pointer',
          'rounded-2xl overflow-hidden',
          'bg-white/80 dark:bg-white/[0.06]',
          'border border-black/[0.04] dark:border-white/10',
          'backdrop-blur-xl',
          'transition-all duration-300 ease-out',
          // 悬停效果
          'hover:bg-white dark:hover:bg-white/[0.09]',
          'hover:shadow-xl hover:shadow-black/[0.08]',
          'hover:scale-[1.01]',
          'hover:border-black/[0.08] dark:hover:border-white/20',
          // 聚焦效果
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
          // 选中态
          isSelected && [
            'bg-gradient-to-br from-primary/[0.06] via-white to-white',
            'dark:from-primary/[0.12] dark:via-white/[0.08] dark:to-white/[0.06]',
            'shadow-lg shadow-black/[0.06]',
          ],
        )}
      >
        <div className="p-4 space-y-3 relative">
          {/* 头部：Logo + 名称 */}
          <div className="flex items-start gap-3">
            {/* Logo */}
            <div
              className={cn(
                'w-11 h-11 rounded-xl flex items-center justify-center shrink-0',
                'shadow-lg shadow-black/10',
                'transition-all duration-300',
                'group-hover:scale-105',
                colors.iconBg,
              )}
            >
              <IconComponent size={20} className="text-white drop-" />
            </div>

            {/* 名称和状态 */}
            <div className="flex-1 min-w-0 pt-0.5">
              <div className="flex items-center gap-2">
                <h4
                  className={cn(
                    'text-sm font-semibold truncate transition-colors',
                    isSelected ? 'text-primary' : 'text-foreground',
                  )}
                >
                  {agent.nameKey?.startsWith('presetAgent.')
                    ? t(agent.nameKey.replace('presetAgent.', '') as any)
                    : agent.name}
                </h4>
                {/* 仅不可用时显示状态 */}
                {!agent.isAvailable && (
                  <span className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] font-medium">
                    <AlertCircle size={10} />
                    {t('notConfigured')}
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2 mt-1 leading-relaxed">
                {agent.descriptionKey?.startsWith('presetAgent.')
                  ? t(agent.descriptionKey.replace('presetAgent.', '') as any)
                  : agent.description}
              </p>
              {agent.tools && agent.tools.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {agent.tools.slice(0, 4).map((toolId) => {
                    const labelKey = `builtinToolNames.${toolId}` as const;
                    const label = tPanel.has(labelKey) ? tPanel(labelKey) : toolId;
                    return (
                      <span
                        key={toolId}
                        className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-muted/40 text-[10px] text-muted-foreground"
                      >
                        {label}
                      </span>
                    );
                  })}
                  {agent.tools.length > 4 && (
                    <span className="text-[10px] text-muted-foreground/70">
                      +{agent.tools.length - 4}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 示例案例区域 */}
          {agent.quickTasks && agent.quickTasks.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] text-muted-foreground/70 uppercase tracking-wider font-medium">
                {t('exampleCases')}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {agent.quickTasks.slice(0, 3).map((task) => {
                  const TaskIcon = iconMap[task.icon || 'FileText'] || FileText;
                  return (
                    <span
                      key={task.id}
                      className={cn(
                        'inline-flex items-center gap-1 px-2 py-1 rounded-full',
                        'text-[11px] font-medium',
                        'bg-muted/30 text-muted-foreground',
                        'transition-colors duration-200',
                        'group-hover:bg-muted/50',
                      )}
                    >
                      <TaskIcon size={10} className={colors.text} />
                      {task.nameKey?.startsWith('presetAgent.')
                        ? t(task.nameKey.replace('presetAgent.', '') as any)
                        : task.name}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* CLI 智能体工作路径 */}
          {isCLI && (
            <CLIWorkingDirectory
              workingDirectory={workingDirectory}
              onWorkingDirectoryChange={onWorkingDirectoryChange}
            />
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * 性能优化：使用 React.memo 避免不必要的重渲染
 */
export default memo(PresetAgentCard);

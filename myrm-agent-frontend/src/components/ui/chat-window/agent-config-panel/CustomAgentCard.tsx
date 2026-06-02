/**
 * 用户自定义智能体卡片组件
 */

import { useMemo, memo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { User } from 'lucide-react';
import { AgentIcon, LucideAgentIcon } from '@/components/agent/agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import type { AgentListItem } from '@/services/agent';
import { customAgentGradients } from './constants';

interface CustomAgentCardProps {
  agent: AgentListItem;
  isSelected: boolean;
  onClick: () => void;
}

/**
 * 用户自定义智能体卡片 - 与预置卡片统一设计风格
 * 无示例案例区域
 */
const CustomAgentCard = ({ agent, isSelected, onClick }: CustomAgentCardProps) => {
  const tAgent = useTranslations('agent');
  const locale = useLocale();
  const displayName = getBuiltinAgentName(agent.id, agent.name, locale);
  const displayDesc = getBuiltinAgentDescription(agent.id, agent.description || '', locale);

  // 解析头像渐变色
  const gradientColor = useMemo(() => {
    if (agent.avatar_url?.startsWith('gradient:')) {
      const index = parseInt(agent.avatar_url.replace('gradient:', ''), 10);
      if (!isNaN(index) && index >= 0 && index < customAgentGradients.length) {
        return customAgentGradients[index];
      }
    }
    // 基于名称生成稳定的颜色索引
    const hash = agent.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return customAgentGradients[hash % customAgentGradients.length];
  }, [agent.avatar_url, agent.name]);

  return (
    <button
      onClick={onClick}
      className={cn(
        'group relative w-full text-left',
        'rounded-xl overflow-hidden',
        'bg-white/60 dark:bg-white/[0.06]',
        'border border-white/70 dark:border-white/10',
        'backdrop-blur-xl',
        'transition-all duration-300 ease-out',
        // 悬停效果
        'hover:bg-white/80 dark:hover:bg-white/[0.09]',
        'hover:shadow-lg hover:shadow-black/5',
        'hover:scale-[1.01]',
        // 选中态 - 柔和高亮
        isSelected && 'border-primary/50 bg-primary/[0.03] dark:bg-primary/[0.08]',
      )}
    >
      {/* 选中态 - 底部渐变条 */}
      {isSelected && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-primary/40 via-primary to-primary/40" />
      )}

      <div className="p-4 space-y-3">
        {/* 头部：Logo + 名称 */}
        <div className="flex items-start gap-3">
          {/* Logo */}
          {(() => {
            const parsed = parseAvatarUrl(agent.avatar_url, agent.id);
            if (parsed?.type === 'icon') {
              return (
                <div className="shrink-0 transition-transform duration-300 group-hover:scale-110">
                  <AgentIcon iconId={parsed.iconId} size="md" className="w-11 h-11" />
                </div>
              );
            }
            if (parsed?.type === 'lucide') {
              return (
                <div className="shrink-0 transition-transform duration-300 group-hover:scale-110">
                  <LucideAgentIcon iconName={parsed.iconName} size="md" className="w-11 h-11" />
                </div>
              );
            }
            return (
              <div
                className={cn(
                  'w-11 h-11 rounded-xl flex items-center justify-center shrink-0',
                  'bg-gradient-to-br shadow-lg shadow-black/10',
                  'transition-transform duration-300',
                  'group-hover:scale-110',
                  gradientColor,
                )}
              >
                <User size={20} className="text-white drop-" />
              </div>
            );
          })()}

          {/* 名称 */}
          <div className="flex-1 min-w-0 pt-0.5">
            <div className="flex items-center gap-1.5">
              <h4
                className={cn(
                  'text-sm font-semibold truncate transition-colors',
                  isSelected ? 'text-primary' : 'text-foreground',
                )}
              >
                {displayName}
              </h4>
              {agent.agent_type === 'team' && (
                <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded-full bg-primary/10 text-primary border border-primary/20">
                  {tAgent('configPanel.teamBadge')}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2 mt-1 leading-relaxed">
              {displayDesc || tAgent('configPanel.noDescription')}
            </p>
          </div>
        </div>
      </div>
    </button>
  );
};

/**
 * 性能优化：使用 React.memo 避免不必要的重渲染
 *
 * 仅在以下情况重新渲染：
 * - agent 对象变化
 * - isSelected 状态变化
 * - onClick 函数引用变化
 */
export default memo(CustomAgentCard);

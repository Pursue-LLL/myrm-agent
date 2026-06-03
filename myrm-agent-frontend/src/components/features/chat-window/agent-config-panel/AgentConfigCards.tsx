'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Skill } from '@/store/skill/types';
import { MCPServiceConfig } from '@/store/config/types';
import { type BuiltinToolId } from '@/store/chat/types';
import { Wand2, Plug, FileText, Wrench, ChevronRight, Plus, Check, Users } from 'lucide-react';

export type ConfigCardType = 'skills' | 'mcp' | 'instruction' | 'builtin_tools' | 'subagents';

interface AgentConfigCardsProps {
  selectedSkills: Skill[];
  selectedMcps: MCPServiceConfig[];
  systemPrompt: string;
  useGlobalInstruction: boolean;
  enabledBuiltinTools: BuiltinToolId[];
  ephemeralSubagents?: Record<string, unknown>;
  onCardClick: (type: ConfigCardType) => void;
  className?: string;
}

// 定义配置项
interface ConfigItem {
  type: ConfigCardType;
  icon: React.ReactNode;
  label: string;
  count: number;
  preview: string;
}

/**
 * 智能体配置卡片组件 - 简洁高级风格
 * 采用统一的灰色调配色，选中时使用低调的强调色
 */
const AgentConfigCards = ({
  selectedSkills,
  selectedMcps,
  systemPrompt,
  useGlobalInstruction,
  enabledBuiltinTools,
  ephemeralSubagents = {},
  onCardClick,
  className,
}: AgentConfigCardsProps) => {
  const t = useTranslations('agent.configPanel');

  const subagentCount = Object.keys(ephemeralSubagents).length;
  const subagentNames = Object.keys(ephemeralSubagents);

  const items: ConfigItem[] = [
    {
      type: 'skills',
      icon: <Wand2 size={16} strokeWidth={1.5} />,
      label: t('skills'),
      count: selectedSkills.length,
      preview:
        selectedSkills.length > 0
          ? selectedSkills
              .slice(0, 2)
              .map((s) => s.name)
              .join(', ') + (selectedSkills.length > 2 ? '...' : '')
          : t('noSelected'),
    },
    {
      type: 'mcp',
      icon: <Plug size={16} strokeWidth={1.5} />,
      label: t('mcp'),
      count: selectedMcps.length,
      preview:
        selectedMcps.length > 0
          ? selectedMcps
              .slice(0, 2)
              .map((m) => m.name)
              .join(', ') + (selectedMcps.length > 2 ? '...' : '')
          : t('noSelected'),
    },
    {
      type: 'builtin_tools',
      icon: <Wrench size={16} strokeWidth={1.5} />,
      label: t('builtinTools'),
      count: enabledBuiltinTools.length,
      preview:
        enabledBuiltinTools.length > 0
          ? enabledBuiltinTools
              .slice(0, 2)
              .map((id) => t(`builtinToolNames.${id}`))
              .join(', ') + (enabledBuiltinTools.length > 2 ? '...' : '')
          : t('noSelected'),
    },
    {
      type: 'subagents',
      icon: <Users size={16} strokeWidth={1.5} />,
      label: t('subagents'),
      count: subagentCount,
      preview:
        subagentCount > 0 ? subagentNames.slice(0, 2).join(', ') + (subagentCount > 2 ? '...' : '') : t('noSelected'),
    },
    {
      type: 'instruction',
      icon: <FileText size={16} strokeWidth={1.5} />,
      label: t('instruction'),
      count: systemPrompt.trim().length > 0 ? 1 : 0,
      preview:
        systemPrompt.trim().length > 0
          ? systemPrompt.slice(0, 30) + (systemPrompt.length > 30 ? '...' : '')
          : useGlobalInstruction
            ? t('useGlobalInstructionDefault')
            : t('noInstruction'),
    },
  ];

  return (
    <div className={cn('grid grid-cols-2 gap-2.5', className)}>
      {items.map((item) => {
        const hasContent = item.count > 0;
        return (
          <button
            key={item.type}
            onClick={() => onCardClick(item.type)}
            className={cn(
              'group relative flex flex-col p-3 rounded-lg',
              'border transition-all duration-200',
              // 选中：毛玻璃效果，不选中：透明
              hasContent ? 'backdrop-blur-md border-primary/15' : 'bg-transparent border-border/30',
              // hover: 只加阴影，不改背景
              'hover:shadow-lg hover:shadow-black/5 dark:hover:shadow-black/20',
              'cursor-pointer text-left',
            )}
            style={
              hasContent
                ? {
                    backgroundColor: 'rgba(255, 255, 255, 0.3)',
                  }
                : undefined
            }
          >
            {/* 头部：图标 + 数量/添加按钮 */}
            <div className="flex items-center justify-between mb-1.5">
              <div
                className={cn(
                  'p-1.5 rounded-full transition-colors',
                  hasContent
                    ? 'bg-primary/10 text-primary'
                    : 'bg-muted/40 text-muted-foreground group-hover:text-foreground',
                )}
              >
                {item.icon}
              </div>
              {hasContent ? (
                <span
                  className={cn(
                    'flex items-center gap-1 text-xs font-medium px-1.5 py-0.5 rounded',
                    'bg-primary/10 text-primary',
                  )}
                >
                  <Check size={10} strokeWidth={2.5} />
                  <span>{item.count}</span>
                </span>
              ) : (
                <Plus size={14} className="text-muted-foreground/50 group-hover:text-primary transition-colors" />
              )}
            </div>

            {/* 标签 */}
            <h4 className={cn('text-sm font-medium mb-0.5', hasContent ? 'text-foreground' : 'text-muted-foreground')}>
              {item.label}
            </h4>

            {/* 预览 */}
            <p className={cn('text-xs truncate', hasContent ? 'text-muted-foreground' : 'text-muted-foreground/50')}>
              {item.preview}
            </p>

            {/* 悬浮箭头 */}
            <ChevronRight
              size={14}
              className={cn(
                'absolute right-2 top-1/2 -translate-y-1/2',
                'opacity-0 group-hover:opacity-100',
                'transition-opacity duration-150',
                'text-muted-foreground',
              )}
            />
          </button>
        );
      })}
    </div>
  );
};

export default AgentConfigCards;

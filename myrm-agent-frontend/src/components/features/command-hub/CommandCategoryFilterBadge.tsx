import React from 'react';
import {
  Compass,
  GitBranch,
  Layers,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useGlobalCommandHubStore } from './useGlobalCommandHubStore';
import type { CommandCategory } from './globalCommandHubTypes';

interface CommandCategoryFilterBadgeProps {
  className?: string;
}

export const CommandCategoryFilterBadge: React.FC<CommandCategoryFilterBadgeProps> = ({
  className = '',
}) => {
  const { activeCategory, setActiveCategory } = useGlobalCommandHubStore();

  const categories: Array<{
    id: CommandCategory;
    label: string;
    icon: React.FC<{ className?: string }>;
  }> = [
    { id: 'all', label: '全部命令', icon: Layers },
    { id: 'navigation', label: '页面导航', icon: Compass },
    { id: 'ai_dispatch', label: 'AI 派工', icon: Sparkles },
    { id: 'action', label: '快捷操作', icon: Zap },
    { id: 'git', label: 'Git 运维', icon: GitBranch },
  ];

  return (
    <div
      role="toolbar"
      aria-label="命令类别筛选栏"
      className={`flex items-center gap-1.5 overflow-x-auto px-4 py-2 border-b border-slate-800/80 bg-slate-900/60 text-xs ${className}`}
    >
      {categories.map((cat) => {
        const Icon = cat.icon;
        const isActive = activeCategory === cat.id;

        return (
          <button
            key={cat.id}
            type="button"
            onClick={() => {
              setActiveCategory(cat.id);
            }}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors shrink-0 ${
              isActive
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
            aria-label={`筛选 ${cat.label}`}
          >
            <Icon className="w-3 h-3" />
            <span>{cat.label}</span>
          </button>
        );
      })}
    </div>
  );
};

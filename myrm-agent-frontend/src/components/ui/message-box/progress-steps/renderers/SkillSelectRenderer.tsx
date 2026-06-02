import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Wand2 } from 'lucide-react';
import type { SkillSelectItem } from '../utils';

interface SkillSelectRendererProps {
  items: SkillSelectItem[];
  messageId: string;
  stepIndex: number;
}

/**
 * 技能选择渲染器
 * 友好展示选择的技能名称和理由
 */
const SkillSelectRenderer: React.FC<SkillSelectRendererProps> = ({ items, messageId, stepIndex }) => {
  // 提取理由（所有项共享同一个理由）
  const reason = items[0]?.reason;

  // 格式化技能名称（将下划线替换为空格，首字母大写）
  const formatSkillName = (name: string): string => {
    return name
      .replace(/_skill$/, '')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase())
      .replace(/-/g, ' ');
  };

  return (
    <div className="flex flex-col gap-1.5">
      {/* 技能徽章列表 */}
      <div className="flex flex-wrap gap-1.5">
        {items.map((item, index) => (
          <div
            key={`${messageId}-step-${stepIndex}-skill-${index}`}
            className={cn(
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md',
              'bg-muted/70',
              'border border-border',
              'text-xs font-medium text-muted-foreground',
              'transition-colors duration-200 hover:bg-muted hover:text-foreground',
            )}
          >
            <Wand2 className="w-3 h-3" />
            <span>{formatSkillName(item.skill_name)}</span>
          </div>
        ))}
      </div>

      {/* 选择理由 */}
      {reason && <p className="text-xs text-muted-foreground/70 leading-relaxed">{reason}</p>}
    </div>
  );
};

export default SkillSelectRenderer;

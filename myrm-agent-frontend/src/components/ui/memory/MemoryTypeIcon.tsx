'use client';

import { memo } from 'react';
import { User, Brain, Clock, Cog, MessageSquare, FileText, ClipboardList } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryType } from '@/store/memory';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useTranslations } from 'next-intl';

interface MemoryTypeIconProps {
  type: MemoryType;
  size?: number;
  className?: string;
  showBackground?: boolean;
  showTooltip?: boolean;
}

const typeConfig: Record<
  MemoryType,
  {
    icon: typeof User;
    label: string;
    bgColor: string;
    iconColor: string;
  }
> = {
  profile: {
    icon: User,
    label: 'Profile',
    bgColor: 'bg-blue-500/10 dark:bg-blue-400/10',
    iconColor: 'text-blue-600 dark:text-blue-400',
  },
  semantic: {
    icon: Brain,
    label: 'Semantic',
    bgColor: 'bg-purple-500/10 dark:bg-purple-400/10',
    iconColor: 'text-purple-600 dark:text-purple-400',
  },
  episodic: {
    icon: Clock,
    label: 'Episodic',
    bgColor: 'bg-amber-500/10 dark:bg-amber-400/10',
    iconColor: 'text-amber-600 dark:text-amber-400',
  },
  procedural: {
    icon: Cog,
    label: 'Procedural',
    bgColor: 'bg-emerald-500/10 dark:bg-emerald-400/10',
    iconColor: 'text-emerald-600 dark:text-emerald-400',
  },
  conversation: {
    icon: MessageSquare,
    label: 'Conversation',
    bgColor: 'bg-green-500/10 dark:bg-green-400/10',
    iconColor: 'text-green-600 dark:text-green-400',
  },
  claim: {
    icon: FileText,
    label: 'Claim',
    bgColor: 'bg-rose-500/10 dark:bg-rose-400/10',
    iconColor: 'text-rose-600 dark:text-rose-400',
  },
  task_digest: {
    icon: ClipboardList,
    label: 'Task Digest',
    bgColor: 'bg-sky-500/10 dark:bg-sky-400/10',
    iconColor: 'text-sky-600 dark:text-sky-400',
  },
};

const MemoryTypeIcon = memo<MemoryTypeIconProps>(
  ({ type, size = 16, className, showBackground = false, showTooltip = false }) => {
    const config = typeConfig[type];
    const Icon = config.icon;
    const t = useTranslations('memory');

    const iconElement = showBackground ? (
      <div className={cn('inline-flex items-center justify-center rounded-lg p-2', config.bgColor, className)}>
        <Icon size={size} className={config.iconColor} />
      </div>
    ) : (
      <Icon size={size} className={cn(config.iconColor, className)} />
    );

    if (!showTooltip) {
      return iconElement;
    }

    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex cursor-help">{iconElement}</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[280px] space-y-1.5">
          <div className="font-medium text-foreground">{t(`types.${type}`)}</div>
          <div className="text-muted-foreground">{t(`typeTooltips.${type}.description`)}</div>
          <div className="text-xs text-muted-foreground/80 pt-1 border-t border-border/50">
            {t(`typeTooltips.${type}.example`)}
          </div>
        </TooltipContent>
      </Tooltip>
    );
  },
);

MemoryTypeIcon.displayName = 'MemoryTypeIcon';

export default MemoryTypeIcon;

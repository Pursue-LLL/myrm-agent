'use client';

import { memo, type ComponentType } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import {
  IconAlertTriangle,
  IconCheckCircle,
  IconXCircle,
  type IconProps,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type { AgentReadinessItem, ReadinessLevel } from '@/services/agent';

// Dimensions the server reports; anything else is shown verbatim rather than guessed at.
const KNOWN_DIMENSIONS = new Set(['model', 'mcp', 'skills', 'tools', 'search', 'deployment']);

const LEVEL_PRESENTATION: Record<ReadinessLevel, { icon: ComponentType<IconProps>; tone: string }> = {
  ready: { icon: IconCheckCircle, tone: 'text-emerald-600 dark:text-emerald-400' },
  warning: { icon: IconAlertTriangle, tone: 'text-amber-600 dark:text-amber-400' },
  blocked: { icon: IconXCircle, tone: 'text-destructive' },
};

interface AgentReadinessListProps {
  items: AgentReadinessItem[];
  /** Offer a settings deep link on items that are not ready. */
  withLinks?: boolean;
  className?: string;
}

/** One row per readiness dimension; shared by the setup wizard and the plugin import result. */
const AgentReadinessList = memo(({ items, withLinks = false, className }: AgentReadinessListProps) => {
  const t = useTranslations('Agent.readiness');

  return (
    <ul className={cn('grid gap-2', className)}>
      {items.map((item) => {
        const { icon: Icon, tone } = LEVEL_PRESENTATION[item.level];
        const label = KNOWN_DIMENSIONS.has(item.dimension)
          ? t(`dimensions.${item.dimension}` as Parameters<typeof t>[0])
          : item.dimension;
        return (
          <li key={item.dimension} className="flex items-start gap-2 rounded-lg border p-3 text-sm">
            <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', tone)} />
            <div className="min-w-0 flex-1">
              <div className="font-medium">{label}</div>
              <div className="mt-0.5 break-words text-xs text-muted-foreground">{item.reason}</div>
            </div>
            {withLinks && item.level !== 'ready' && item.settings_path && (
              <Link href={item.settings_path} className="shrink-0 text-xs font-medium text-primary hover:underline">
                {t('fix')}
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
});

AgentReadinessList.displayName = 'AgentReadinessList';

export default AgentReadinessList;

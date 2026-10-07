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

const LEVEL_PRESENTATION: Record<ReadinessLevel, { icon: ComponentType<IconProps>; tone: string }> = {
  ready: { icon: IconCheckCircle, tone: 'text-emerald-600 dark:text-emerald-400' },
  warning: { icon: IconAlertTriangle, tone: 'text-amber-600 dark:text-amber-400' },
  blocked: { icon: IconXCircle, tone: 'text-destructive' },
};

/** A finding can list dozens of servers or keys; a row names the first few and signals there are more. */
const MAX_NAMES_SHOWN = 3;

function summarizeNames(names: string[]): string {
  const shown = names.slice(0, MAX_NAMES_SHOWN).join(', ');
  return names.length > MAX_NAMES_SHOWN ? `${shown}…` : shown;
}

interface AgentReadinessListProps {
  items: AgentReadinessItem[];
  /** Offer a settings deep link on items that are not ready. */
  withLinks?: boolean;
  className?: string;
}

/**
 * One row per readiness finding; shared by the setup wizard and the plugin import result.
 * The backend's English `reason` is a diagnostic and is never shown: rows speak through the finding
 * `code`, and a code or dimension this build does not know falls back to a generic localized line.
 */
const AgentReadinessList = memo(({ items, withLinks = false, className }: AgentReadinessListProps) => {
  const t = useTranslations('Agent.readiness');
  const has = (key: string) => t.has(key as Parameters<typeof t.has>[0]);
  const translate = (key: string, values?: Record<string, string | number>) =>
    t(key as Parameters<typeof t>[0], values);

  return (
    <ul className={cn('grid gap-2', className)}>
      {items.map((item) => {
        const { icon: Icon, tone } = LEVEL_PRESENTATION[item.level];
        const label = has(`dimensions.${item.dimension}`)
          ? translate(`dimensions.${item.dimension}`)
          : translate('dimensions.other');
        const reason = has(`reasons.${item.code}`)
          ? translate(`reasons.${item.code}`, { names: summarizeNames(item.names), count: item.count })
          : translate(`fallback.${item.level}`);
        return (
          <li key={`${item.dimension}:${item.code}`} className="flex items-start gap-2 rounded-lg border p-3 text-sm">
            <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', tone)} />
            <div className="min-w-0 flex-1">
              <div className="font-medium">{label}</div>
              <div className="mt-0.5 break-words text-xs text-muted-foreground">{reason}</div>
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

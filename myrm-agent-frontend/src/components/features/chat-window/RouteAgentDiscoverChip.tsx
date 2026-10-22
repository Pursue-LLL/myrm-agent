'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n localization)
 * - next/navigation::useRouter (POS: navigation to agent settings/fleet)
 * - lucide-react::Cpu, ShieldCheck, Sparkles, X, ChevronRight (POS: iconography)
 * - @/lib/utils/classnameUtils::cn
 * - @/lib/utils/a11y::activateOnKey
 *
 * [OUTPUT]
 * - RouteAgentDiscoverChip: CapabilityOwnerFit intelligent dispatch & specialist discovery capsule.
 *
 * [POS]
 * EmptyChat and chat composition header discoverability component. Educates users on specialized
 * capability owner agents (Coder, Reviewer, Researcher, Architect, Security Auditor) and
 * anti-misrouting guardrails.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { ChevronRight, Cpu, ShieldCheck, Sparkles, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { activateOnKey } from '@/lib/utils/a11y';

export interface RouteAgentDiscoverChipProps {
  className?: string;
  onSelectAgent?: (agentType: string) => void;
}

const DISMISS_KEY = 'myrm_route_agent_discover_chip_dismissed';

interface SpecialistAgentBadge {
  agentType: string;
  labelKey: string;
  colorClass: string;
}

const SPECIALIST_PREVIEWS: readonly SpecialistAgentBadge[] = [
  { agentType: 'coder', labelKey: 'coder', colorClass: 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20' },
  { agentType: 'code-reviewer', labelKey: 'reviewer', colorClass: 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/20' },
  { agentType: 'researcher', labelKey: 'researcher', colorClass: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20' },
  { agentType: 'architect', labelKey: 'architect', colorClass: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20' },
  { agentType: 'security-auditor', labelKey: 'auditor', colorClass: 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20' },
];

export const RouteAgentDiscoverChip = memo(function RouteAgentDiscoverChip({
  className,
  onSelectAgent,
}: RouteAgentDiscoverChipProps) {
  const t = useTranslations('chat.routeAgentDiscoverChip');
  const router = useRouter();
  const [dismissed, setDismissed] = useState<boolean>(true);

  useEffect(() => {
    try {
      const isDismissed = sessionStorage.getItem(DISMISS_KEY) === 'true';
      setDismissed(isDismissed);
    } catch {
      setDismissed(false);
    }
  }, []);

  const handleNavigate = useCallback(() => {
    router.push('/agents?view=fleet&tab=capabilities');
  }, [router]);

  const handleDismiss = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      sessionStorage.setItem(DISMISS_KEY, 'true');
    } catch {
      // Ignore sessionStorage errors
    }
    setDismissed(true);
  }, []);

  const handleBadgeClick = useCallback(
    (e: React.MouseEvent, agentType: string) => {
      e.stopPropagation();
      if (onSelectAgent) {
        onSelectAgent(agentType);
      } else {
        router.push(`/agents?view=fleet&focus=${encodeURIComponent(agentType)}`);
      }
    },
    [onSelectAgent, router],
  );

  if (dismissed) {
    return null;
  }

  return (
    <div
      data-testid="route-agent-discover-chip"
      onClick={handleNavigate}
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- clickable card with nested action buttons
      role="button"
      tabIndex={0}
      onKeyDown={activateOnKey}
      aria-label={t('title')}
      className={cn(
        'group relative w-full flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl cursor-pointer select-none',
        'bg-gradient-to-r from-indigo-500/5 via-sky-500/5 to-cyan-500/5 dark:from-indigo-950/20 dark:via-sky-950/20 dark:to-cyan-950/20',
        'border border-indigo-500/20 dark:border-indigo-500/15 hover:border-indigo-500/35 dark:hover:border-indigo-500/30',
        'shadow-xs hover:shadow-sm transition-all duration-200',
        className,
      )}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 shrink-0 group-hover:scale-105 transition-transform">
          <Cpu className="w-4 h-4" />
        </div>
        <div className="flex flex-col min-w-0 text-left">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 truncate">
              {t('title')}
            </span>
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded-md bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/20 shrink-0">
              <ShieldCheck className="w-2.5 h-2.5" />
              {t('guardrailBadge')}
            </span>
          </div>
          <span className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate">
            {t('subtitle')}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 justify-between sm:justify-end shrink-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          {SPECIALIST_PREVIEWS.map((spec) => (
            <button
              key={spec.agentType}
              type="button"
              data-testid={`badge-${spec.agentType}`}
              onClick={(e) => handleBadgeClick(e, spec.agentType)}
              className={cn(
                'inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded-md border transition-transform hover:scale-105',
                spec.colorClass,
              )}
            >
              <Sparkles className="w-2.5 h-2.5" />
              {t(`specialists.${spec.labelKey}`)}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-1">
          <span className="hidden md:inline-flex items-center gap-0.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 group-hover:text-indigo-700 dark:group-hover:text-indigo-300 transition-colors">
            {t('action')}
            <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </span>
          <button
            type="button"
            onClick={handleDismiss}
            className="p-1 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-200/50 dark:hover:bg-neutral-800/50 transition-colors"
            aria-label={t('dismiss')}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
});

export default RouteAgentDiscoverChip;

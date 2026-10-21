/**
 * [INPUT]
 * - next-intl::useTranslations
 * - next/link
 * - lucide-react icons
 *
 * [OUTPUT]
 * - FleetKPIBar: Fleet KPI metrics banner for agents page
 *
 * [POS]
 * Extracted from app/agents/page.tsx to keep page under 400 lines limit.
 */

'use client';

import React from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Activity, Zap, Coins, ShieldAlert } from 'lucide-react';

interface FleetKPIBarProps {
  kpi: {
    onlineAgents: number;
    monthTokens: number;
    monthCost: number;
    pendingApprovals: number;
  };
}

function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}K`;
  }
  return String(count);
}

function formatCost(usd: number): string {
  if (usd >= 100) {
    return `$${usd.toFixed(0)}`;
  }
  if (usd >= 1) {
    return `$${usd.toFixed(2)}`;
  }
  return `$${usd.toFixed(3)}`;
}

function KPICard({
  icon,
  label,
  value,
  highlight,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: boolean;
  href?: string;
}) {
  if (href) {
    return (
      <Link
        href={href}
        className={`rounded-lg border p-3 flex items-center gap-3 bg-card transition-colors ${
          highlight ? 'border-orange-500/50 hover:border-orange-500/70' : 'hover:bg-accent/50'
        }`}
        data-testid="fleet-pending-approvals-link"
      >
        <div className="shrink-0">{icon}</div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground truncate">{label}</p>
          <p className={`text-lg font-semibold tabular-nums ${highlight ? 'text-orange-500' : ''}`}>{value}</p>
        </div>
      </Link>
    );
  }
  return (
    <div
      className={`rounded-lg border p-3 flex items-center gap-3 bg-card ${
        highlight ? 'border-orange-500/50' : ''
      }`}
    >
      <div className="shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground truncate">{label}</p>
        <p className={`text-lg font-semibold tabular-nums ${highlight ? 'text-orange-500' : ''}`}>{value}</p>
      </div>
    </div>
  );
}

export function FleetKPIBar({ kpi }: FleetKPIBarProps) {
  const t = useTranslations('Agent.fleet');

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <KPICard
        icon={<Activity className="h-4 w-4 text-green-500" />}
        label={t('kpi.online', { fallback: 'Online' })}
        value={String(kpi.onlineAgents)}
      />
      <KPICard
        icon={<Zap className="h-4 w-4 text-blue-500" />}
        label={t('kpi.monthTokens', { fallback: 'Month Tokens' })}
        value={formatTokens(kpi.monthTokens)}
      />
      <KPICard
        icon={<Coins className="h-4 w-4 text-amber-500" />}
        label={t('kpi.monthCost', { fallback: 'Month Cost' })}
        value={formatCost(kpi.monthCost)}
      />
      <KPICard
        icon={<ShieldAlert className="h-4 w-4 text-orange-500" />}
        label={t('kpi.pending', { fallback: 'Pending' })}
        value={String(kpi.pendingApprovals)}
        highlight={kpi.pendingApprovals > 0}
        href={kpi.pendingApprovals > 0 ? '/settings/kanban?status=in_review' : undefined}
      />
    </div>
  );
}

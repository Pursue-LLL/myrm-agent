'use client';

import { ShieldCheck } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  MemoryImportCoverageItem,
  MigrationLanePreviewItem,
  SessionMigrationPreviewItem,
  TokenEconomicsComparison,
} from '@/services/memory/archive';

import { COVERAGE_LABEL_KEYS, type TranslationFn } from './wizardShared';

export function CoverageMatrix({ items, t }: { items: MemoryImportCoverageItem[]; t: TranslationFn }) {
  if (items.length === 0) {
    return null;
  }

  const statusStyles: Record<string, string> = {
    ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
    review: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    manual: 'border-border/60 bg-secondary/30 text-muted-foreground',
    missing: 'border-destructive/30 bg-destructive/10 text-destructive',
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{t('preview.coverageTitle')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <div
            key={item.key}
            className={cn('rounded-lg border px-3 py-2.5 text-xs', statusStyles[item.status] ?? statusStyles.manual)}
          >
            <div className="font-medium">
              {COVERAGE_LABEL_KEYS.has(item.label) ? t(`preview.coverageLabels.${item.label}`) : item.label}
            </div>
            <div className="mt-0.5 opacity-80">{t(`preview.coverageStatus.${item.status}`)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MigrationLaneMatrix({ lanes, t }: { lanes: MigrationLanePreviewItem[]; t: TranslationFn }) {
  if (lanes.length === 0) {
    return null;
  }

  const statusStyles: Record<string, string> = {
    ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
    review: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    manual: 'border-border/60 bg-secondary/30 text-muted-foreground',
    missing: 'border-destructive/30 bg-destructive/10 text-destructive',
    warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    critical: 'border-destructive/30 bg-destructive/10 text-destructive',
    pending: 'border-border/60 bg-secondary/30 text-muted-foreground',
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{t('preview.lanesTitle')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {lanes.map((lane) => (
          <div
            key={lane.lane}
            className={cn('rounded-lg border px-3 py-2.5 text-xs', statusStyles[lane.status] ?? statusStyles.manual)}
          >
            <div className="font-medium">{t(`preview.laneLabels.${lane.label}`, { defaultValue: lane.label })}</div>
            <div className="mt-1 text-muted-foreground">{lane.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function HermesArchitectureMappingCard({ t }: { t: TranslationFn }) {
  const mappingRows = [
    {
      source: 'USER.md',
      target: t('preview.hermesMapping.userMdTarget'),
      desc: t('preview.hermesMapping.userMdDesc'),
    },
    {
      source: 'MEMORY.md',
      target: t('preview.hermesMapping.memoryMdTarget'),
      desc: t('preview.hermesMapping.memoryMdDesc'),
    },
    {
      source: 'session search',
      target: t('preview.hermesMapping.sessionSearchTarget'),
      desc: t('preview.hermesMapping.sessionSearchDesc'),
    },
    {
      source: 'external MCP (8 plugins)',
      target: t('preview.hermesMapping.externalMcpTarget'),
      desc: t('preview.hermesMapping.externalMcpDesc'),
    },
  ];

  return (
    <div
      data-testid="hermes-architecture-mapping-card"
      className="space-y-3 rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
          <h3 className="text-sm font-medium text-foreground">{t('preview.hermesMapping.title')}</h3>
        </div>
        <Badge variant="outline" className="text-[10px] border-indigo-500/30 text-indigo-700 dark:text-indigo-300">
          {t('preview.hermesMapping.badge')}
        </Badge>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 text-xs">
        {mappingRows.map((row) => (
          <div key={row.source} className="rounded-lg border border-border/40 bg-background/60 p-2.5 space-y-1">
            <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-indigo-700 dark:text-indigo-300">
              <span>{row.source}</span>
              <span className="text-muted-foreground font-sans">→</span>
              <span className="font-sans font-medium text-foreground truncate">{row.target}</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">{row.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SessionPreviewCard({ sessions, t }: { sessions: SessionMigrationPreviewItem[]; t: TranslationFn }) {
  if (sessions.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4 text-left">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          {t('preview.sessionsTitle', { count: sessions.length })}
        </h3>
        <Badge variant="secondary" className="text-[10px] bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
          {t('preview.resumptionReady')}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">{t('preview.sessionsDesc')}</p>
      <div className="max-h-48 overflow-y-auto space-y-1.5 divide-y divide-border/20">
        {sessions.map((s) => (
          <div key={s.session_id} className="pt-1.5 first:pt-0 flex items-center justify-between text-xs">
            <span className="truncate font-medium text-foreground max-w-[65%]">{s.title || s.session_id}</span>
            <span className="text-[11px] text-muted-foreground">
              {t('preview.turnsCount', { turns: s.turn_count, tools: s.tool_call_count })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TokenEconomicsCard({
  data,
  sourceName,
  t,
}: {
  data: TokenEconomicsComparison;
  sourceName: string;
  t: TranslationFn;
}) {
  const sourcePercent = 100;
  const myrmPercent =
    data.source_tokens_per_turn > 0 ? Math.round((data.myrm_tokens_per_turn / data.source_tokens_per_turn) * 100) : 0;

  return (
    <div className="space-y-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">{t('preview.tokenEconomics.title')}</h3>
        <Badge variant="default" className="text-[10px] bg-emerald-600 hover:bg-emerald-700">
          {t('preview.tokenEconomics.savings', { percent: data.savings_percent })}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        {t('preview.tokenEconomics.description', { count: data.skill_count })}
      </p>
      <div className="space-y-2.5">
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{sourceName}</span>
            <span className="tabular-nums font-medium">{data.source_tokens_per_turn.toLocaleString()} tokens</span>
          </div>
          <div className="h-2 rounded-full bg-secondary overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500/70 transition-all"
              style={{ width: `${sourcePercent}%` }}
            />
          </div>
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Myrm</span>
            <span className="tabular-nums font-medium text-emerald-600 dark:text-emerald-400">
              {data.myrm_tokens_per_turn.toLocaleString()} tokens
            </span>
          </div>
          <div className="h-2 rounded-full bg-secondary overflow-hidden">
            <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${myrmPercent}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}

export function SummaryCell({
  label,
  value,
  className = '',
}: {
  label: string;
  value: string | number;
  className?: string;
}) {
  return (
    <div className="rounded-xl border border-border/50 bg-secondary/20 p-3">
      <div className="text-[11px] text-muted-foreground/60 mb-1">{label}</div>
      <div className={cn('text-lg font-semibold tabular-nums', className)}>{value}</div>
    </div>
  );
}

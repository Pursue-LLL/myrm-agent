'use client';

/**
 * [INPUT]
 * @/services/memory/domainMesh::DomainBucketOverview, ProgressiveHighlight
 * lucide-react::User, Bot, CheckSquare, Sparkles, ChevronRight, Layers
 *
 * [OUTPUT]
 * DomainMeshCard: Visual card rendering a single memory domain (User, Assistant, Task)
 * with category distribution chips and L0/L1 progressive highlights.
 *
 * [POS]
 * Component layer for progressive retrieval mesh exploration.
 */

import React from 'react';
import { User, Bot, CheckSquare, ChevronRight, Layers } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { DomainBucketOverview, ProgressiveHighlight } from '@/services/memory/domainMesh';

interface DomainMeshCardProps {
  domain: 'user' | 'assistant' | 'task';
  title: string;
  subtitle: string;
  data?: DomainBucketOverview;
  onSelectHighlight: (highlight: ProgressiveHighlight) => void;
  className?: string;
}

const DOMAIN_ICONS: Record<string, React.ReactNode> = {
  user: <User className="h-4 w-4 text-sky-500 dark:text-sky-400" />,
  assistant: <Bot className="h-4 w-4 text-purple-500 dark:text-purple-400" />,
  task: <CheckSquare className="h-4 w-4 text-emerald-500 dark:text-emerald-400" />,
};

const DOMAIN_ACCENTS: Record<string, { border: string; bg: string; badge: string }> = {
  user: {
    border: 'border-sky-500/20 hover:border-sky-500/40',
    bg: 'from-sky-500/5 to-transparent',
    badge: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
  },
  assistant: {
    border: 'border-purple-500/20 hover:border-purple-500/40',
    bg: 'from-purple-500/5 to-transparent',
    badge: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
  },
  task: {
    border: 'border-emerald-500/20 hover:border-emerald-500/40',
    bg: 'from-emerald-500/5 to-transparent',
    badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  },
};

export const DomainMeshCard: React.FC<DomainMeshCardProps> = ({
  domain,
  title,
  subtitle,
  data,
  onSelectHighlight,
  className,
}) => {
  const accent = DOMAIN_ACCENTS[domain] || DOMAIN_ACCENTS.user;
  const icon = DOMAIN_ICONS[domain] || <Layers className="h-4 w-4 text-muted-foreground" />;

  const total = data?.total_count ?? 0;
  const highlights = data?.highlights ?? [];
  const categories = Object.entries(data?.category_counts ?? {});

  return (
    <div
      className={cn(
        'group flex flex-col rounded-xl border bg-card/60 bg-gradient-to-b p-4 shadow-sm backdrop-blur-sm transition-all duration-200',
        accent.border,
        accent.bg,
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background/80 shadow-xs border border-border/50">
            {icon}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground tracking-tight">{title}</h3>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
        </div>
        <span
          className={cn(
            'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold tabular-nums',
            accent.badge,
          )}
        >
          {total}
        </span>
      </div>

      {/* Category Pills */}
      {categories.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {categories.map(([cat, count]) => (
            <span
              key={cat}
              className="inline-flex items-center gap-1 rounded-md bg-accent/40 px-1.5 py-0.5 text-[11px] font-medium text-foreground/80 border border-border/40"
            >
              <span className="capitalize">{cat}</span>
              <span className="text-muted-foreground/70 tabular-nums">({count})</span>
            </span>
          ))}
        </div>
      )}

      {/* Highlights List */}
      <div className="mt-4 flex flex-1 flex-col gap-2">
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">
          Highlights & Insights
        </div>

        {highlights.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
            No memories indexed in this domain yet.
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {highlights.slice(0, 4).map((h) => (
              <button
                key={h.id}
                type="button"
                onClick={() => onSelectHighlight(h)}
                className="group/item flex w-full flex-col gap-1 rounded-lg border border-border/40 bg-background/50 p-2.5 text-left transition-colors hover:border-border hover:bg-accent/40"
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="line-clamp-1 text-xs font-medium text-foreground group-hover/item:text-primary">
                    {h.l0 || 'Untitled Memory'}
                  </span>
                  <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground/50 transition-transform group-hover/item:translate-x-0.5 group-hover/item:text-foreground" />
                </div>
                {h.l1 && (
                  <p className="line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                    {h.l1}
                  </p>
                )}
                <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground/70">
                  <span className="rounded bg-accent/60 px-1 py-0.2 capitalize">
                    {h.category}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Brain, Search, Database } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/primitives/hover-card';

interface MemoryInsightPanelProps {
  memoryBudget?: { used: number; total: number };
  citations?: string[];
  className?: string;
}

export default function MemoryInsightPanel({ memoryBudget, citations, className }: MemoryInsightPanelProps) {
  const t = useTranslations('memoryInsight');
  
  if (!memoryBudget && (!citations || citations.length === 0)) {
    return null;
  }

  const budgetPct = memoryBudget ? Math.round((memoryBudget.used / memoryBudget.total) * 100) : 0;
  
  return (
    <div className={cn("flex flex-wrap items-center gap-2 mt-2", className)}>
      {/* Memory Budget Pill */}
      {memoryBudget && (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-secondary/60 text-muted-foreground border border-border/50 cursor-help transition-colors hover:bg-secondary">
              <Brain size={12} className={cn("shrink-0", budgetPct > 80 ? "text-amber-500" : "text-primary/70")} />
              <span>{t('budgetPill', { pct: budgetPct })}</span>
            </div>
          </HoverCardTrigger>
          <HoverCardContent align="start" className="w-64 p-3 z-50">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold">
                <span>{t('budgetTitle')}</span>
                <span className={budgetPct > 80 ? "text-amber-500" : ""}>{budgetPct}%</span>
              </div>
              <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                <div 
                  className={cn("h-full transition-all duration-500", budgetPct > 80 ? "bg-amber-500" : "bg-primary")}
                  style={{ width: `${Math.min(100, budgetPct)}%` }}
                />
              </div>
              <div className="text-[11px] text-muted-foreground flex justify-between">
                <span>{t('budgetUsed', { chars: memoryBudget.used.toLocaleString() })}</span>
                <span>{t('budgetLimit', { chars: memoryBudget.total.toLocaleString() })}</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed">
                {t('budgetDescription')}
              </p>
            </div>
          </HoverCardContent>
        </HoverCard>
      )}

      {/* Citations Pill */}
      {citations && citations.length > 0 && (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-primary/5 text-primary border border-primary/10 cursor-help transition-colors hover:bg-primary/10">
              <Search size={12} className="shrink-0" />
              <span>{t('citationsPill', { count: citations.length })}</span>
            </div>
          </HoverCardTrigger>
          <HoverCardContent align="start" className="w-64 p-3 z-50">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-foreground mb-1">
                <Database size={12} className="text-primary" />
                <span>{t('citationsTitle')}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t('citationsDescription')}
              </p>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {citations.map((id) => (
                  <span key={id} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground">
                    {id}
                  </span>
                ))}
              </div>
            </div>
          </HoverCardContent>
        </HoverCard>
      )}
    </div>
  );
}

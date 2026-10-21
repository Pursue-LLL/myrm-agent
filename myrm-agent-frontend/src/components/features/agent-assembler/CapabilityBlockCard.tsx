'use client';

/**
 * Capability Block Card Component for Visual Modular Agent Assembler.
 *
 * [INPUT] block: CapabilityBlock, onToggle, onRemove, onUpdateConfig
 * [OUTPUT] CapabilityBlockCard: Modular card with category badges, status switch, and config drawer.
 * [POS] src/components/features/agent-assembler/CapabilityBlockCard.tsx
 */

import { memo, useState } from 'react';
import {
  Brain,
  Sparkles,
  Wrench,
  BookOpen,
  Database,
  ShieldCheck,
  ChevronDown,
  Trash2,
  Settings,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { CapabilityBlock, CapabilityBlockCategory } from './assemblerTypes';

export interface CapabilityBlockCardProps {
  block: CapabilityBlock;
  onToggle?: (id: string) => void;
  onRemove?: (id: string) => void;
  onUpdateConfig?: (id: string, config: CapabilityBlock['config']) => void;
  className?: string;
}

const CATEGORY_STYLES: Record<
  CapabilityBlockCategory,
  {
    icon: typeof Brain;
    badgeBg: string;
    border: string;
    text: string;
  }
> = {
  brain: {
    icon: Brain,
    badgeBg: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
    border: 'border-purple-500/30 hover:border-purple-500/60',
    text: 'text-purple-600 dark:text-purple-400',
  },
  persona: {
    icon: Sparkles,
    badgeBg: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    border: 'border-amber-500/30 hover:border-amber-500/60',
    text: 'text-amber-600 dark:text-amber-400',
  },
  tools: {
    icon: Wrench,
    badgeBg: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
    border: 'border-sky-500/30 hover:border-sky-500/60',
    text: 'text-sky-600 dark:text-sky-400',
  },
  skills: {
    icon: BookOpen,
    badgeBg: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    border: 'border-emerald-500/30 hover:border-emerald-500/60',
    text: 'text-emerald-600 dark:text-emerald-400',
  },
  memory: {
    icon: Database,
    badgeBg: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
    border: 'border-indigo-500/30 hover:border-indigo-500/60',
    text: 'text-indigo-600 dark:text-indigo-400',
  },
  sandbox: {
    icon: ShieldCheck,
    badgeBg: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
    border: 'border-rose-500/30 hover:border-rose-500/60',
    text: 'text-rose-600 dark:text-rose-400',
  },
};

export const CapabilityBlockCard = memo(function CapabilityBlockCard({
  block,
  onToggle,
  onRemove,
  onUpdateConfig,
  className,
}: CapabilityBlockCardProps) {
  const t = useTranslations('agentAssembler');
  const [expanded, setExpanded] = useState(false);

  const style = CATEGORY_STYLES[block.category];
  const IconComponent = style.icon;

  const handleToggle = () => {
    if (onToggle) {
      onToggle(block.id);
    }
  };

  const handleRemove = () => {
    if (onRemove) {
      onRemove(block.id);
    }
  };

  return (
    <div
      className={cn(
        'group rounded-xl border bg-card p-3.5 shadow-sm transition-all duration-200',
        style.border,
        !block.enabled && 'opacity-60 bg-muted/20 border-dashed',
        className,
      )}
      data-testid={`capability-block-card-${block.id}`}
    >
      <div className="flex items-start justify-between gap-2.5">
        <div className="flex items-start gap-2.5 min-w-0 flex-1">
          <div
            className={cn(
              'p-2 rounded-lg flex-shrink-0 transition-colors',
              style.badgeBg,
            )}
          >
            <IconComponent className="h-4 w-4" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-foreground truncate">
                {block.name}
              </span>
              <span
                className={cn(
                  'text-[10px] px-1.5 py-0.2 rounded font-mono uppercase tracking-wider',
                  style.badgeBg,
                )}
              >
                {block.category}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
              {block.description}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            onClick={handleToggle}
            className={cn(
              'px-2 py-0.5 rounded text-[10px] font-medium transition-colors border',
              block.enabled
                ? 'bg-primary/10 border-primary/30 text-primary hover:bg-primary/20'
                : 'bg-muted border-border text-muted-foreground hover:bg-muted/80',
            )}
            title={block.enabled ? t('enabled') || 'Enabled' : t('disabled') || 'Disabled'}
          >
            {block.enabled ? t('active') || 'Active' : t('inactive') || 'Inactive'}
          </button>

          <button
            type="button"
            onClick={() => {
              setExpanded((prev) => !prev);
            }}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
            title={t('configure') || 'Configure'}
          >
            <ChevronDown
              className={cn(
                'h-3.5 w-3.5 transition-transform duration-150',
                expanded && 'rotate-180',
              )}
            />
          </button>

          {onRemove && (
            <button
              type="button"
              onClick={handleRemove}
              className="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
              title={t('remove') || 'Remove'}
              aria-label={`Remove block ${block.name}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pt-2.5 border-t border-border/50 text-[11px] flex flex-col gap-2">
          <div className="flex items-center gap-1.5 font-medium text-muted-foreground">
            <Settings className="h-3 w-3" />
            <span>{t('blockParameters') || 'Parameters & Injected Config'}</span>
          </div>

          <div className="bg-muted/40 p-2 rounded-lg font-mono text-[10px] max-h-32 overflow-y-auto">
            {Object.entries(block.config).length > 0 ? (
              <div className="flex flex-col gap-1">
                {Object.entries(block.config).map(([k, v]) => (
                  <div key={k} className="flex items-start gap-1.5">
                    <span className="text-muted-foreground font-semibold">{k}:</span>
                    <span className="text-foreground break-all">
                      {Array.isArray(v) ? v.join(', ') : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-muted-foreground italic">
                {t('noExtraConfig') || 'Standard preset parameters applied.'}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

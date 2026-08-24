'use client';

import React, { useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertCircle, AlertTriangle, Info, CheckCircle2, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';

export type ReviewSeverityType = 'critical' | 'warning' | 'info';

export interface ReviewCommentItem {
  message: string;
  severity?: ReviewSeverityType;
  target_path?: string | null;
  line_range?: string | null;
  fix_suggestion?: string | null;
  id?: string | null;
}

export interface AcceptanceResultItem {
  label?: string;
  passed?: boolean;
  reason?: string;
  error_logs?: string | null;
  duration_ms?: number;
  comments?: ReviewCommentItem[];
}

interface ReviewCommentThreadProps {
  results: AcceptanceResultItem[];
  t: (key: string) => string;
  onInitiateFix?: (comment: ReviewCommentItem) => void;
  className?: string;
}

const SEVERITY_CONFIG: Record<
  ReviewSeverityType,
  {
    icon: typeof AlertCircle;
    badgeBg: string;
    badgeText: string;
    border: string;
    labelKey: string;
  }
> = {
  critical: {
    icon: AlertCircle,
    badgeBg: 'bg-destructive/10',
    badgeText: 'text-destructive',
    border: 'border-destructive/30',
    labelKey: 'reviewSeverityCritical',
  },
  warning: {
    icon: AlertTriangle,
    badgeBg: 'bg-amber-500/10',
    badgeText: 'text-amber-600 dark:text-amber-400',
    border: 'border-amber-500/30',
    labelKey: 'reviewSeverityWarning',
  },
  info: {
    icon: Info,
    badgeBg: 'bg-blue-500/10',
    badgeText: 'text-blue-600 dark:text-blue-400',
    border: 'border-blue-500/30',
    labelKey: 'reviewSeverityInfo',
  },
};

export function ReviewCommentThread({ results, t, onInitiateFix, className }: ReviewCommentThreadProps) {
  const [selectedSeverity, setSelectedSeverity] = useState<ReviewSeverityType | 'all'>('all');
  const [expandedSuggestions, setExpandedSuggestions] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Extract and normalize all comments
  const allComments: Array<ReviewCommentItem & { criterionLabel?: string }> = [];
  results.forEach((res, rIdx) => {
    const rawComments = Array.isArray(res.comments) ? res.comments : [];
    if (rawComments.length > 0) {
      rawComments.forEach((c) => {
        allComments.push({
          ...c,
          severity: c.severity || (res.passed === false ? 'critical' : 'info'),
          criterionLabel: res.label || `${t('completionCriteria')} #${rIdx + 1}`,
        });
      });
    } else if (res.passed === false && res.reason) {
      // Fallback critical comment from failure reason
      allComments.push({
        severity: 'critical',
        message: res.reason,
        criterionLabel: res.label || `${t('completionCriteria')} #${rIdx + 1}`,
      });
    }
  });

  const criticalTotal = allComments.filter((c) => c.severity === 'critical').length;
  const warningTotal = allComments.filter((c) => c.severity === 'warning').length;
  const infoTotal = allComments.filter((c) => c.severity === 'info').length;

  const filteredComments =
    selectedSeverity === 'all' ? allComments : allComments.filter((c) => c.severity === selectedSeverity);

  const toggleSuggestion = (key: string) => {
    setExpandedSuggestions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className={cn('space-y-2', className)}>
      {/* Criteria passed summary cards */}
      <div className="space-y-1">
        {results.map((item, idx) => (
          <div
            key={idx}
            className="flex items-start gap-1.5 text-xs rounded bg-muted/30 px-2 py-1 border border-border/50"
          >
            <span
              className={cn(
                'mt-0.5 inline-block w-2 h-2 rounded-full shrink-0',
                item.passed ? 'bg-emerald-500' : 'bg-destructive',
              )}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-1">
                <p className="text-[11px] font-medium text-foreground/90 truncate">
                  {item.label || `${t('completionCriteria')} #${idx + 1}`}
                </p>
                <span
                  className={cn(
                    'text-[10px] shrink-0 font-medium',
                    item.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive',
                  )}
                >
                  {item.passed ? t('acceptancePassed') : t('acceptanceFailed')}
                  {typeof item.duration_ms === 'number' && (
                    <span className="text-muted-foreground/60 ml-1 font-mono text-[9px]">{item.duration_ms}ms</span>
                  )}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Review Comments Thread Section */}
      {allComments.length > 0 && (
        <div className="rounded border border-border/70 bg-background/50 p-2 space-y-2">
          {/* Header & Filter Pills */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              {t('reviewCommentsTitle')} ({allComments.length})
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setSelectedSeverity('all')}
                className={cn(
                  'text-[9px] px-1.5 py-0.5 rounded-full border transition-colors',
                  selectedSeverity === 'all'
                    ? 'bg-foreground/10 font-semibold border-foreground/30 text-foreground'
                    : 'text-muted-foreground border-transparent hover:bg-muted',
                )}
              >
                {t('reviewFilterAll')} ({allComments.length})
              </button>
              {criticalTotal > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedSeverity('critical')}
                  className={cn(
                    'text-[9px] px-1.5 py-0.5 rounded-full border transition-colors',
                    selectedSeverity === 'critical'
                      ? 'bg-destructive/15 text-destructive font-semibold border-destructive/40'
                      : 'text-destructive/80 border-transparent hover:bg-destructive/10',
                  )}
                >
                  {t('reviewSeverityCritical')} ({criticalTotal})
                </button>
              )}
              {warningTotal > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedSeverity('warning')}
                  className={cn(
                    'text-[9px] px-1.5 py-0.5 rounded-full border transition-colors',
                    selectedSeverity === 'warning'
                      ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 font-semibold border-amber-500/40'
                      : 'text-amber-600/80 dark:text-amber-400/80 border-transparent hover:bg-amber-500/10',
                  )}
                >
                  {t('reviewSeverityWarning')} ({warningTotal})
                </button>
              )}
              {infoTotal > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedSeverity('info')}
                  className={cn(
                    'text-[9px] px-1.5 py-0.5 rounded-full border transition-colors',
                    selectedSeverity === 'info'
                      ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400 font-semibold border-blue-500/40'
                      : 'text-blue-600/80 dark:text-blue-400/80 border-transparent hover:bg-blue-500/10',
                  )}
                >
                  {t('reviewSeverityInfo')} ({infoTotal})
                </button>
              )}
            </div>
          </div>

          {/* Comment List */}
          <div className="space-y-1.5">
            {filteredComments.map((comment, idx) => {
              const sev = (comment.severity || 'critical') as ReviewSeverityType;
              const config = SEVERITY_CONFIG[sev] || SEVERITY_CONFIG.critical;
              const Icon = config.icon;
              const itemKey = `comment-${idx}-${comment.target_path || ''}`;
              const isExpanded = !!expandedSuggestions[itemKey];

              return (
                <div
                  key={idx}
                  className={cn(
                    'rounded border px-2 py-1.5 text-xs space-y-1 transition-all',
                    config.border,
                    config.badgeBg,
                  )}
                >
                  <div className="flex items-start justify-between gap-1">
                    <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                      <Icon className={cn('w-3.5 h-3.5 shrink-0', config.badgeText)} />
                      <span
                        className={cn(
                          'text-[9px] uppercase font-bold px-1 py-0.2 rounded',
                          config.badgeText,
                          'bg-background/80',
                        )}
                      >
                        {t(config.labelKey)}
                      </span>
                      {comment.target_path && (
                        <span className="font-mono text-[10px] text-foreground/80 px-1 py-0.2 rounded bg-muted/60 border border-border/40 truncate max-w-[200px]">
                          {comment.target_path}
                          {comment.line_range && `:${comment.line_range}`}
                        </span>
                      )}
                    </div>

                    {onInitiateFix && comment.severity === 'critical' && (
                      <button
                        type="button"
                        onClick={() => onInitiateFix(comment)}
                        className="text-[9px] px-1.5 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shrink-0 font-medium"
                      >
                        {t('reviewFixAction')}
                      </button>
                    )}
                  </div>

                  <p className="text-[11px] text-foreground/90 break-words leading-relaxed pl-5">{comment.message}</p>

                  {/* Fix Suggestion Foldable Card */}
                  {comment.fix_suggestion && (
                    <div className="pl-5 pt-0.5">
                      <button
                        type="button"
                        onClick={() => toggleSuggestion(itemKey)}
                        className="flex items-center gap-1 text-[10px] text-primary/80 hover:text-primary transition-colors font-medium"
                      >
                        {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        <span>{t('reviewFixSuggestion')}</span>
                      </button>

                      {isExpanded && (
                        <div className="mt-1 rounded border border-border/60 bg-background/80 p-1.5 text-[10px] text-muted-foreground space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[9px] text-primary/70">{t('reviewAdviceSnippet')}</span>
                            <button
                              type="button"
                              onClick={() => handleCopy(comment.fix_suggestion || '', itemKey)}
                              className="text-muted-foreground hover:text-foreground transition-colors p-0.5"
                              title={t('copy')}
                            >
                              {copiedId === itemKey ? (
                                <Check className="w-3 h-3 text-emerald-500" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                          <p className="font-mono text-[10px] text-foreground/90 whitespace-pre-wrap break-words">
                            {comment.fix_suggestion}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

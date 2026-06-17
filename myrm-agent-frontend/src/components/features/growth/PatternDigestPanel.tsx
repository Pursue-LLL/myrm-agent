'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Sparkles, Loader2, ChevronDown, ChevronUp, Play, Lightbulb, Sprout } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest, showApiError } from '@/lib/api';

interface DiscoveredPattern {
  title: string;
  description: string;
  evidence_summary: string;
  durability: string;
  confidence: number;
  actionable_suggestion: string;
}

interface PatternDiscoveryEvent {
  id: string;
  occurred_at: string | null;
  summary: string;
  metadata: {
    operation?: string;
    pattern_count?: number;
    memory_count?: number;
    duration_ms?: number;
    meta_observation?: string;
    patterns?: DiscoveredPattern[];
  };
}

interface TriggerResult {
  triggered: boolean;
  skipped?: boolean;
  reason?: string;
  pattern_count?: number;
  error?: string;
}

export default function PatternDigestPanel() {
  const t = useTranslations('growthDashboard.patternDigest');
  const [events, setEvents] = useState<PatternDiscoveryEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiRequest<PatternDiscoveryEvent[]>('/memory/guardian/pattern-discoveries?limit=10');
      setEvents(data);
    } catch (e) {
      showApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const handleTrigger = async () => {
    try {
      setTriggering(true);
      const result = await apiRequest<TriggerResult>('/memory/guardian/trigger-pattern-discovery', {
        method: 'POST',
      });
      if (result.error) {
        showApiError(new Error(result.error));
      } else if (result.skipped) {
        showApiError(new Error(result.reason || t('triggerSkipped')));
      } else if (result.pattern_count === 0) {
        showApiError(new Error(t('triggerNoNewPatterns')));
      } else {
        await fetchEvents();
      }
    } catch (e) {
      showApiError(e);
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const latestEvent = events[0];
  const patterns = latestEvent?.metadata?.patterns ?? [];

  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4 text-center px-4">
        <Sprout className="h-14 w-14 text-muted-foreground/40" />
        <h3 className="text-lg font-semibold text-foreground">{t('emptyTitle')}</h3>
        <p className="text-sm text-muted-foreground max-w-md">{t('emptyDescription')}</p>
        <Button variant="outline" size="sm" onClick={handleTrigger} disabled={triggering} className="mt-2">
          {triggering ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
          {triggering ? t('triggering') : t('triggerButton')}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-500" />
            {t('title')}
          </h3>
          <p className="text-sm text-muted-foreground mt-0.5">{t('description')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleTrigger} disabled={triggering} className="self-start shrink-0">
          {triggering ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Play className="h-4 w-4 mr-1.5" />}
          {triggering ? t('triggering') : t('triggerButton')}
        </Button>
      </div>

      {/* Latest report summary */}
      {latestEvent && (
        <p className="text-xs text-muted-foreground">
          {t('patternCount', { count: patterns.length })}
          {latestEvent.occurred_at && (
            <> · {t('discoveredAt')}: {new Date(latestEvent.occurred_at).toLocaleDateString()}</>
          )}
        </p>
      )}

      {/* Pattern cards */}
      {patterns.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground">{t('noPatterns')}</CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {patterns.map((pattern, idx) => {
            const cardId = `${latestEvent.id}-${idx}`;
            const expanded = expandedId === cardId;
            return (
              <Card key={cardId} className="transition-shadow hover:shadow-sm">
                <CardContent className="p-4">
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => setExpandedId(expanded ? null : cardId)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-medium text-foreground leading-tight">{pattern.title}</h4>
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{pattern.description}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <DurabilityBadge durability={pattern.durability} t={t} />
                        <ConfidenceBadge confidence={pattern.confidence} />
                        {expanded ? (
                          <ChevronUp className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        )}
                      </div>
                    </div>
                  </button>

                  {expanded && (
                    <div className="mt-3 pt-3 border-t space-y-2.5">
                      {pattern.actionable_suggestion && (
                        <div className="flex items-start gap-2">
                          <Lightbulb className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                          <p className="text-xs text-foreground">{pattern.actionable_suggestion}</p>
                        </div>
                      )}
                      {pattern.evidence_summary && (
                        <div className="bg-muted/50 rounded-md p-2.5">
                          <p className="text-xs text-muted-foreground font-medium mb-1">{t('evidence')}</p>
                          <p className="text-xs text-foreground/80">{pattern.evidence_summary}</p>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);
  return (
    <span
      className={cn(
        'text-[10px] font-medium px-1.5 py-0.5 rounded-full',
        percent >= 80
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
          : percent >= 60
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
      )}
    >
      {percent}%
    </span>
  );
}

function DurabilityBadge({ durability, t }: { durability: string; t: (key: string) => string }) {
  const label = t(`durabilityStages.${durability}`) || durability;
  return (
    <span
      className={cn(
        'text-[10px] font-medium px-1.5 py-0.5 rounded-full',
        durability === 'established'
          ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
          : durability === 'declining'
            ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
            : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
      )}
    >
      {label}
    </span>
  );
}

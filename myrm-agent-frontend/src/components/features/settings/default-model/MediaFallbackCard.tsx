'use client';

import { useCallback, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { IconRefresh } from '@/components/features/icons/PremiumIcons';
import type { VisionHealthResult } from '@/services/llm-config';
import ModelSelectRow from './ModelSelectRow';
import type { ModelSlotId } from './modelSlots';

type HealthState = 'idle' | 'checking' | 'done';

export interface FallbackHealth {
  state: HealthState;
  result: VisionHealthResult | null;
  check: () => Promise<void>;
}

/** Probes a fallback endpoint on demand; an unreachable server is reported as an unconfigured, unhealthy result. */
export function useFallbackHealthCheck(probe: () => Promise<VisionHealthResult>, networkError: string): FallbackHealth {
  const [state, setState] = useState<HealthState>('idle');
  const [result, setResult] = useState<VisionHealthResult | null>(null);

  const check = useCallback(async () => {
    setState('checking');
    setResult(null);
    try {
      setResult(await probe());
    } catch {
      setResult({ configured: false, healthy: false, error: networkError });
    } finally {
      setState('done');
    }
  }, [probe, networkError]);

  return { state, result, check };
}

export interface FallbackHealthCopy {
  test: string;
  checking: string;
  unknown: string;
  notConfigured: string;
  okHint: string;
  ok: (latencyMs: number) => string;
  failed: (error: string) => string;
  failedModel: (model: string) => string;
  failedEndpoint: (endpoint: string) => string;
  resolvedModel: (configured: string, resolved: string) => string;
}

function FallbackHealthRow({ health, copy }: { health: FallbackHealth; copy: FallbackHealthCopy }) {
  const { state, result, check } = health;
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <button
        type="button"
        onClick={check}
        disabled={state === 'checking'}
        className="inline-flex items-center gap-2 rounded-lg border border-border bg-secondary/50 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60"
      >
        <IconRefresh className={`h-3.5 w-3.5 ${state === 'checking' ? 'animate-spin' : ''}`} />
        {state === 'checking' ? copy.checking : copy.test}
      </button>
      {state === 'done' && result && (
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className={`text-xs ${result.healthy ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>
            {result.healthy
              ? copy.ok(result.latency_ms ?? 0)
              : result.configured
                ? copy.failed(result.error ?? copy.unknown)
                : copy.notConfigured}
          </span>
          {!result.healthy && result.configured && result.model && (
            <span className="text-[11px] text-muted-foreground break-all">{copy.failedModel(result.model)}</span>
          )}
          {!result.healthy && result.configured && result.base_url && (
            <span className="text-[11px] text-muted-foreground break-all">{copy.failedEndpoint(result.base_url)}</span>
          )}
          {result.healthy && (
            <>
              <span className="text-[11px] text-muted-foreground">{copy.okHint}</span>
              {result.resolved_model && result.model && result.resolved_model !== result.model && (
                <span className="text-[11px] text-amber-600 dark:text-amber-400 break-all">
                  {copy.resolvedModel(result.model, result.resolved_model)}
                </span>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export interface MediaFallbackCopy {
  title: string;
  description: string;
  fallbackDescription: string;
  selectFallback: string;
  health: FallbackHealthCopy;
}

interface MediaFallbackCardProps {
  icon: ReactNode;
  copy: MediaFallbackCopy;
  primarySlot: ModelSlotId;
  fallbackSlot: ModelSlotId;
  health: FallbackHealth;
  /** Shown between the description and the health check. */
  children?: ReactNode;
}

/** A primary + fallback model pair for a media input (vision, video), with an on-demand health check. */
export default function MediaFallbackCard({
  icon,
  copy,
  primarySlot,
  fallbackSlot,
  health,
  children,
}: MediaFallbackCardProps) {
  const t = useTranslations('settings.defaultModel');
  return (
    <div className="p-5 bg-background/50 rounded-xl border border-border/50">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <span className="text-sm font-medium text-foreground">{copy.title}</span>
      </div>
      <p className="text-xs text-muted-foreground mb-4">{copy.description}</p>
      {children}
      <FallbackHealthRow health={health} copy={copy.health} />
      <ModelSelectRow slot={primarySlot} label={t('selectModel')} />
      <p className="text-xs text-muted-foreground mt-4 mb-4">{copy.fallbackDescription}</p>
      <ModelSelectRow slot={fallbackSlot} label={copy.selectFallback} />
    </div>
  );
}

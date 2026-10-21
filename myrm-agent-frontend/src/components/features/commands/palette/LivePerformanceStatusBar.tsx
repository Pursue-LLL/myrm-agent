'use client';

/**
 * LivePerformanceStatusBar Component.
 * Real-time status bar telemetry with Cache Hit %, TTFT, Tokens/sec, and Global E-Stop.
 * Implements Hermes Agent v0.21.0 status bar telemetry parity with zero emojis.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  Clock,
  Database,
  OctagonAlert,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { TelemetryMetrics } from './globalCommandPaletteTypes';

interface LivePerformanceStatusBarProps {
  metrics?: TelemetryMetrics;
  onTriggerEStop?: () => Promise<void> | void;
  className?: string;
}

const DEFAULT_METRICS: TelemetryMetrics = {
  cache_hit_rate: 84.5,
  ttft_ms: 240,
  throughput_tokens_per_sec: 142.5,
  estop_active: false,
};

export const LivePerformanceStatusBar: React.FC<LivePerformanceStatusBarProps> = ({
  metrics = DEFAULT_METRICS,
  onTriggerEStop,
  className = '',
}) => {
  // Safe translation fallback
  let t = (key: string): string => key;
  try {
    const translator = useTranslations('commandPalette.telemetry');
    t = (key: string) => translator(key);
  } catch {
    // Fallback in tests
  }

  const [isEstopTriggered, setIsEstopTriggered] = useState<boolean>(metrics.estop_active);
  const [isConfirmingEstop, setIsConfirmingEstop] = useState<boolean>(false);

  const handleEStop = async () => {
    if (!isConfirmingEstop) {
      setIsConfirmingEstop(true);
      return;
    }

    setIsEstopTriggered(true);
    setIsConfirmingEstop(false);

    try {
      if (onTriggerEStop) {
        await onTriggerEStop();
      } else {
        await fetch('/api/v1/security/estop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'activate',
            reason: 'Global physical E-Stop triggered via status bar',
          }),
        });
      }
    } catch {
      // Fallback
    }
  };

  return (
    <aside
      aria-label="Live Telemetry Status Bar"
      className={`h-9 border-t border-slate-800 bg-slate-950/95 px-4 flex items-center justify-between text-xs font-mono select-none text-slate-400 ${className}`}
    >
      {/* Telemetry Metric Pills */}
      <div className="flex items-center gap-3 min-w-0">
        {/* 1. Prompt Cache Hit % */}
        <div
          title="Prompt Cache Hit Rate"
          className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900/80 border border-slate-800 text-slate-300"
        >
          <Database className="h-3 w-3 text-emerald-400" />
          <span className="text-[10px] text-slate-400">{t('cacheHit')}:</span>
          <span className="font-semibold text-emerald-400">
            {metrics.cache_hit_rate.toFixed(1)}%
          </span>
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
        </div>

        {/* 2. TTFT (Time To First Token) */}
        <div
          title="Time To First Token (Latency)"
          className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900/80 border border-slate-800 text-slate-300"
        >
          <Clock className="h-3 w-3 text-cyan-400" />
          <span className="text-[10px] text-slate-400">{t('ttft')}:</span>
          <span className="font-semibold text-cyan-300">{metrics.ttft_ms}ms</span>
        </div>

        {/* 3. Tokens / Sec Throughput */}
        <div
          title="Real-Time Generation Rate"
          className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900/80 border border-slate-800 text-slate-300"
        >
          <Zap className="h-3 w-3 text-indigo-400" />
          <span className="text-[10px] text-slate-400">{t('throughput')}:</span>
          <span className="font-semibold text-indigo-300">
            {metrics.throughput_tokens_per_sec.toFixed(1)} tok/s
          </span>
        </div>
      </div>

      {/* Right Controls: E-Stop & System Heartbeat */}
      <div className="flex items-center gap-2">
        {isEstopTriggered ? (
          <div className="flex items-center gap-1 px-2.5 py-0.5 rounded bg-red-950 border border-red-800 text-red-300 text-[11px] font-semibold">
            <OctagonAlert className="h-3.5 w-3.5 text-red-400 animate-bounce" />
            <span>{t('estopActivated')}</span>
          </div>
        ) : (
          <button
            type="button"
            onClick={handleEStop}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all ${
              isConfirmingEstop
                ? 'bg-red-600 hover:bg-red-500 text-white animate-pulse'
                : 'bg-red-950/60 hover:bg-red-900/80 border border-red-800/80 text-red-300'
            }`}
          >
            <OctagonAlert className="h-3.5 w-3.5" />
            <span>{isConfirmingEstop ? 'Confirm E-Stop?' : t('estopBtn')}</span>
          </button>
        )}

        <div className="flex items-center gap-1 text-[10px] text-slate-400 pl-2 border-l border-slate-800">
          <Activity className="h-3 w-3 text-emerald-400" />
          <span>Hermes Telemetry</span>
        </div>
      </div>
    </aside>
  );
};

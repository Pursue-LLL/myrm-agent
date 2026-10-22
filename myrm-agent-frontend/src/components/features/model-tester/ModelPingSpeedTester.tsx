'use client';

/**
 * Instant Model Latency and Protocol Health Speed Tester Component.
 *
 * [INPUT] modelId, provider, modelTesterService
 * [OUTPUT] ModelPingSpeedTester: Compact button/badge for instant TTFT and throughput validation.
 * [POS] src/components/features/model-tester/ModelPingSpeedTester.tsx
 */

import { memo, useState, useCallback } from 'react';
import {
  Zap,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { ModelPingResponseDTO } from './modelTesterTypes';
import { modelTesterService } from './modelTesterService';

export interface ModelPingSpeedTesterProps {
  modelId: string;
  provider?: string;
  className?: string;
  onTested?: (result: ModelPingResponseDTO) => void;
}

export const ModelPingSpeedTester = memo(function ModelPingSpeedTester({
  modelId,
  provider = 'openai',
  className,
  onTested,
}: ModelPingSpeedTesterProps) {
  const t = useTranslations('extensionWidgets');
  const [isTesting, setIsTesting] = useState(false);
  const [result, setResult] = useState<ModelPingResponseDTO | null>(null);

  const handleTest = useCallback(async () => {
    if (isTesting || !modelId) {
      return;
    }
    setIsTesting(true);
    try {
      const res = await modelTesterService.pingModel({
        model_id: modelId,
        provider,
      });
      setResult(res);
      if (onTested) {
        onTested(res);
      }
    } finally {
      setIsTesting(false);
    }
  }, [isTesting, modelId, provider, onTested]);

  const renderBadge = () => {
    if (!result) {
      return null;
    }

    if (result.status === 'unreachable') {
      return (
        <div
          className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-[11px]"
          title={result.error_message || 'Endpoint unreachable'}
        >
          <XCircle className="h-3 w-3 flex-shrink-0" />
          <span className="font-semibold">{t('unreachable') || 'Unreachable'}</span>
        </div>
      );
    }

    const isDegraded = result.status === 'degraded' || result.ttft_ms > 1500;
    return (
      <div
        className={cn(
          'flex items-center gap-2 px-2 py-0.5 rounded-md border text-[11px]',
          isDegraded
            ? 'bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-400'
            : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-400',
        )}
      >
        {isDegraded ? (
          <AlertTriangle className="h-3 w-3 flex-shrink-0 text-amber-500" />
        ) : (
          <CheckCircle2 className="h-3 w-3 flex-shrink-0 text-emerald-500" />
        )}
        <span className="font-mono font-semibold">{result.ttft_ms}ms</span>
        {result.tokens_per_second > 0 && (
          <span className="text-[10px] opacity-75 font-mono">
            {result.tokens_per_second} tok/s
          </span>
        )}
      </div>
    );
  };

  return (
    <div
      className={cn('inline-flex items-center gap-1.5 text-xs', className)}
      data-testid="model-ping-speed-tester"
    >
      <button
        type="button"
        onClick={handleTest}
        disabled={isTesting}
        aria-label="Test model latency"
        className={cn(
          'inline-flex items-center gap-1 px-2.5 py-1 rounded-md border text-xs font-medium transition-all select-none',
          'bg-muted/40 hover:bg-muted/80 border-border/60 text-foreground',
          'focus:outline-none focus:ring-1 focus:ring-primary/40 active:scale-98',
          isTesting && 'opacity-70 cursor-wait',
        )}
      >
        {isTesting ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            <span>{t('testing') || 'Testing...'}</span>
          </>
        ) : result ? (
          <>
            <RefreshCw className="h-3 w-3 text-muted-foreground" />
            <span>{t('retest') || 'Retest'}</span>
          </>
        ) : (
          <>
            <Zap className="h-3.5 w-3.5 text-amber-500 fill-amber-500/20" />
            <span>{t('testLatency') || 'Test Latency'}</span>
          </>
        )}
      </button>

      {renderBadge()}
    </div>
  );
});

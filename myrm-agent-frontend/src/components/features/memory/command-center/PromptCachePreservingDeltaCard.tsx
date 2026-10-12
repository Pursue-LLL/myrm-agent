'use client';

/**
 * [INPUT]
 * @/services/memory/ephemeralDelta::getActiveEphemeralDeltas, getEphemeralDeltaSnapshot,
 *   getPromptCacheMetrics, previewDeltaInjection, recordEphemeralDelta,
 *   EphemeralDeltaItemDTO, PromptCacheMetricsDTO, PreviewDeltaInjectionResponseDTO,
 *   RecordDeltaRequestDTO
 * ./EphemeralDeltaLiveInspectorView::EphemeralDeltaLiveInspectorView
 * ./PromptCacheConsolidationView::PromptCacheConsolidationView
 *
 * [OUTPUT]
 * PromptCachePreservingDeltaCard: Command center card for session-scoped memory updates.
 *
 * [POS]
 * Primary UI Card for Item 98 (PromptCachePreservingEphemeralDeltaMemorySuite).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Lock, Zap, Layers, RefreshCw, Terminal } from 'lucide-react';
import {
  getEphemeralDeltaSnapshot,
  getPromptCacheMetrics,
  previewDeltaInjection,
  recordEphemeralDelta,
  type EphemeralDeltaItemDTO,
  type PreviewDeltaInjectionResponseDTO,
  type PromptCacheMetricsDTO,
  type RecordDeltaRequestDTO,
} from '@/services/memory/ephemeralDelta';
import { EphemeralDeltaLiveInspectorView } from './EphemeralDeltaLiveInspectorView';
import { PromptCacheConsolidationView } from './PromptCacheConsolidationView';

type ActiveTab = 'live_deltas' | 'cache_consolidation';

interface PromptCachePreservingDeltaCardProps {
  defaultChatId?: string | null;
}

export function PromptCachePreservingDeltaCard({
  defaultChatId,
}: PromptCachePreservingDeltaCardProps): React.JSX.Element {
  const t = useTranslations('memory.commandCenter.promptCache.card');
  const [sessionId, setSessionId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<ActiveTab>('live_deltas');
  const [deltas, setDeltas] = useState<EphemeralDeltaItemDTO[]>([]);
  const [metrics, setMetrics] = useState<PromptCacheMetricsDTO | null>(null);
  const [preview, setPreview] = useState<PreviewDeltaInjectionResponseDTO | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    const normalized = (defaultChatId ?? '').trim();
    if (normalized) {
      setSessionId(normalized);
    }
  }, [defaultChatId]);

  const loadSessionData = useCallback(async (targetSession: string) => {
    const normalized = targetSession.trim();
    if (!normalized) {
      setDeltas([]);
      setMetrics(null);
      return;
    }
    setLoading(true);
    try {
      const [snapshotRes, metricsRes] = await Promise.all([
        getEphemeralDeltaSnapshot(normalized),
        getPromptCacheMetrics(normalized),
      ]);
      setDeltas(snapshotRes.active_deltas ?? []);
      setMetrics(metricsRes);
    } catch {
      setDeltas([]);
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSimulatePreview = useCallback(async () => {
    const normalized = sessionId.trim();
    if (!normalized) {
      return;
    }
    setLoading(true);
    try {
      const res = await previewDeltaInjection({
        session_id: normalized,
      });
      setPreview(res);
      setMetrics(res.metrics);
    } catch {
      setPreview(null);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const handleRecordDelta = async (request: RecordDeltaRequestDTO) => {
    try {
      await recordEphemeralDelta(request);
    } catch {
      const newItem: EphemeralDeltaItemDTO = {
        delta_id: `delta_local_${Date.now()}`,
        session_id: request.session_id,
        target_key: request.target_key,
        content: request.content,
        action: request.action ?? 'override',
        turn_index: request.turn_index ?? 1,
        source: request.source ?? 'user_explicit',
        confidence: request.confidence ?? 1.0,
        created_at: new Date().toISOString(),
        is_reconciled: false,
      };
      setDeltas((prev) => [
        ...prev.filter((d) => d.target_key.toLowerCase() !== newItem.target_key.toLowerCase()),
        newItem,
      ]);
    }
    await loadSessionData(sessionId);
    await handleSimulatePreview();
  };

  useEffect(() => {
    if (!sessionId.trim()) {
      return;
    }
    void loadSessionData(sessionId);
    void handleSimulatePreview();
  }, [sessionId, loadSessionData, handleSimulatePreview]);

  return (
    <Card className="border-border bg-card/80 backdrop-blur shadow-sm">
      <CardHeader className="pb-3 border-b border-border/50">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <Lock className="w-5 h-5 text-emerald-500" />
              <CardTitle className="text-base font-semibold">{t('title')}</CardTitle>
              <Badge variant="outline" className="text-[10px] text-emerald-600 border-emerald-500/40">
                {t('badge')}
              </Badge>
            </div>
            <CardDescription className="text-xs">{t('description')}</CardDescription>
          </div>

          <div className="flex items-center space-x-2">
            <div className="flex items-center space-x-1.5 bg-muted/40 px-2 py-1 rounded border border-border">
              <Terminal className="w-3.5 h-3.5 text-muted-foreground" />
              <input
                id="ephemeral-session-id-input"
                aria-label={t('sessionInputLabel')}
                type="text"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                className="w-36 sm:w-44 text-xs bg-transparent text-foreground focus:outline-none font-mono"
                placeholder={t('sessionPlaceholder')}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void loadSessionData(sessionId)}
              disabled={loading || !sessionId.trim()}
              className="text-xs focus:ring-2 focus:ring-primary"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1 pt-3">
          <Button
            type="button"
            variant={activeTab === 'live_deltas' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setActiveTab('live_deltas')}
            className="text-xs focus:ring-2 focus:ring-primary"
          >
            <Zap className="w-3.5 h-3.5 mr-1" />
            {t('tabLive', { count: deltas.length })}
          </Button>
          <Button
            type="button"
            variant={activeTab === 'cache_consolidation' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setActiveTab('cache_consolidation')}
            className="text-xs focus:ring-2 focus:ring-primary"
          >
            <Layers className="w-3.5 h-3.5 mr-1" />
            {t('tabPreview')}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="pt-4">
        {activeTab === 'live_deltas' ? (
          <EphemeralDeltaLiveInspectorView
            sessionId={sessionId}
            deltas={deltas}
            isReconciled={false}
            onRecordDelta={handleRecordDelta}
            isLoading={loading}
          />
        ) : (
          <PromptCacheConsolidationView
            sessionId={sessionId}
            preview={preview}
            metrics={metrics}
            onSimulatePreview={handleSimulatePreview}
            isLoading={loading}
          />
        )}
      </CardContent>
    </Card>
  );
}

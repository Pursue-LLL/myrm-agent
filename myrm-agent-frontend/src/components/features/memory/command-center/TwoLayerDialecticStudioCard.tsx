'use client';

/**
 * [INPUT]
 * @/services/memory/twoLayerDialectic
 * ./TwoLayerDialecticHudBar
 * ./BaseContextCacheView
 * ./DialecticReconciliationConsoleView
 * ./DialecticCadenceControlsView
 * ./twoLayerDialecticFallbacks
 *
 * [OUTPUT]
 * TwoLayerDialecticStudioCard: Main command-center panel for Item 112.
 *
 * [POS]
 * Command-center card for Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation Suite.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 350 lines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Layers,
  Sparkles,
  Sliders,
  AlertCircle,
  Database,
  Cpu,
} from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import {
  assembleTwoLayerInjection,
  getBaseContextCache,
  inspectDialecticConflicts,
  reconcileDialecticConflicts,
  resetSessionCadence,
  type BaseContextPayloadDTO,
  type DialecticCadenceConfigDTO,
  type DialecticConflictCandidateDTO,
  type DialecticReconciliationResultDTO,
} from '@/services/memory/twoLayerDialectic';
import { TwoLayerDialecticHudBar } from './TwoLayerDialecticHudBar';
import { BaseContextCacheView } from './BaseContextCacheView';
import { DialecticReconciliationConsoleView } from './DialecticReconciliationConsoleView';
import { DialecticCadenceControlsView } from './DialecticCadenceControlsView';
import {
  FALLBACK_BASE_CONTEXT,
  FALLBACK_CADENCE_CONFIG,
  FALLBACK_CONFLICTS,
  FALLBACK_RECONCILIATION_RESULTS,
} from './twoLayerDialecticFallbacks';

type ActiveTab = 'base' | 'dialectic' | 'knobs';

export const TwoLayerDialecticStudioCard: React.FC = () => {
  const t = useTranslations('memory.commandCenter.promptCache.twoLayerStudio');
  const [activeTab, setActiveTab] = useState<ActiveTab>('base');
  const [sessionId, setSessionId] = useState<string>('lab_session_preview');
  const [baseContext, setBaseContext] = useState<BaseContextPayloadDTO | null>(
    FALLBACK_BASE_CONTEXT,
  );
  const [conflicts, setConflicts] = useState<DialecticConflictCandidateDTO[]>(
    FALLBACK_CONFLICTS,
  );
  const [reconciliationResults, setReconciliationResults] = useState<
    DialecticReconciliationResultDTO[]
  >(FALLBACK_RECONCILIATION_RESULTS);
  const [cadenceConfig, setCadenceConfig] = useState<DialecticCadenceConfigDTO>(
    FALLBACK_CADENCE_CONFIG,
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    const normalized = sessionId.trim();
    if (!normalized) {
      return;
    }
    setLoading(true);
    try {
      const fetchedCache = await getBaseContextCache(normalized);
      if (fetchedCache) {
        setBaseContext(fetchedCache);
      } else {
        setBaseContext(FALLBACK_BASE_CONTEXT);
      }

      const inspected = await inspectDialecticConflicts({
        statements: [
          '系统采用 SQLite 作为本地单机轻量级存储引擎。',
          '在分布式高并发云托管生产集群中，存储层切换至 PostgreSQL 架构。',
        ],
      });
      if (inspected && inspected.length > 0) {
        setConflicts(inspected);
      }
    } catch {
      setBaseContext(FALLBACK_BASE_CONTEXT);
      setConflicts(FALLBACK_CONFLICTS);
      setReconciliationResults(FALLBACK_RECONCILIATION_RESULTS);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleForceRefreshBase = async () => {
    const normalized = sessionId.trim();
    if (!normalized || !baseContext) {
      return;
    }
    setLoading(true);
    try {
      const nextTurn = (baseContext.refreshed_at_turn ?? 0) + 1;
      await assembleTwoLayerInjection({
        session_id: normalized,
        turn: nextTurn,
        session_summary: baseContext.session_summary,
        peer_cards: baseContext.standing_peer_cards,
        context_cadence: cadenceConfig.context_cadence,
        dialectic_cadence: cadenceConfig.dialectic_cadence,
        force_refresh_base: true,
      });
      const cached = await getBaseContextCache(normalized);
      if (cached) {
        setBaseContext(cached);
      }
      setBannerMessage(t('refreshSuccess'));
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      setBannerMessage(t('refreshFailed'));
      setTimeout(() => setBannerMessage(null), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleReconcile = async (statements: string[], depth: number) => {
    setLoading(true);
    try {
      const results = await reconcileDialecticConflicts({
        statements,
        depth,
      });
      if (results && results.length > 0) {
        setReconciliationResults(results);
        setBannerMessage(t('reconcileSuccess', { depth, count: results.length }));
      } else {
        setReconciliationResults(FALLBACK_RECONCILIATION_RESULTS);
        setBannerMessage(t('reconcileFallback'));
      }
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      setReconciliationResults(FALLBACK_RECONCILIATION_RESULTS);
      setBannerMessage(t('reconcileOffline'));
      setTimeout(() => setBannerMessage(null), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleResetSession = async () => {
    const normalized = sessionId.trim();
    if (!normalized) {
      return;
    }
    try {
      await resetSessionCadence(normalized);
      setBannerMessage(t('resetSuccess'));
    } catch {
      setBannerMessage(t('resetLocal'));
    }
    setTimeout(() => setBannerMessage(null), 3000);
  };

  const handleUpdateConfig = (newConfig: DialecticCadenceConfigDTO) => {
    setCadenceConfig(newConfig);
    setBannerMessage(t('configApplied'));
    setTimeout(() => setBannerMessage(null), 3000);
  };

  return (
    <div
      aria-label={t('ariaLabel')}
      className="rounded-xl border border-border bg-card p-5 space-y-4 shadow-sm"
    >
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200 leading-relaxed">
        {t('labOnlyBanner')}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1.5 flex-1 max-w-md">
          <Label htmlFor="two-layer-session-id" className="text-xs text-muted-foreground">
            {t('sessionInputLabel')}
          </Label>
          <Input
            id="two-layer-session-id"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder={t('sessionPlaceholder')}
            className="h-9 text-sm"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-foreground tracking-tight">
                {t('title')}
              </h2>
              <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-primary/10 text-primary border border-primary/20">
                {t('itemBadge')}
              </span>
              <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                {t('layoutBadge')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{t('description')}</p>
          </div>
        </div>

        <nav
          aria-label={t('tabsAria')}
          className="flex flex-wrap items-center gap-1 bg-muted p-1 rounded-lg text-xs"
        >
          <button
            type="button"
            aria-label={t('tabBaseAria')}
            onClick={() => setActiveTab('base')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'base'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>{t('tabBase')}</span>
          </button>
          <button
            type="button"
            aria-label={t('tabDialecticAria')}
            onClick={() => setActiveTab('dialectic')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'dialectic'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{t('tabDialectic', { count: conflicts.length })}</span>
          </button>
          <button
            type="button"
            aria-label={t('tabKnobsAria')}
            onClick={() => setActiveTab('knobs')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'knobs'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>{t('tabKnobs')}</span>
          </button>
        </nav>
      </div>

      <TwoLayerDialecticHudBar
        contextCadence={cadenceConfig.context_cadence}
        dialecticCadence={cadenceConfig.dialectic_cadence}
        dialecticDepth={cadenceConfig.dialectic_depth}
        reasoningLevel={cadenceConfig.dialectic_reasoning_level}
        refreshing={loading}
        onRefresh={() => void loadData()}
        onResetSession={() => void handleResetSession()}
      />

      {bannerMessage ? (
        <div className="flex items-center gap-2 p-2.5 rounded-md bg-primary/10 border border-primary/20 text-xs text-primary">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{bannerMessage}</span>
        </div>
      ) : null}

      {activeTab === 'base' &&
        (baseContext ? (
          <BaseContextCacheView
            baseContext={baseContext}
            onForceRefresh={() => void handleForceRefreshBase()}
            refreshing={loading}
          />
        ) : (
          <div className="p-6 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
            {t('emptyBase')}
          </div>
        ))}

      {activeTab === 'dialectic' && (
        <DialecticReconciliationConsoleView
          conflicts={conflicts}
          reconciliationResults={reconciliationResults}
          onReconcile={handleReconcile}
          reconciling={loading}
        />
      )}

      {activeTab === 'knobs' && (
        <DialecticCadenceControlsView
          config={cadenceConfig}
          onUpdateConfig={handleUpdateConfig}
        />
      )}
    </div>
  );
};

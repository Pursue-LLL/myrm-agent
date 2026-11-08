/**
 * [INPUT] @/lib/api::apiRequest (POS: 前端统一请求入口), @/services/wikiService (POS: Wiki 接口: 统计、健康报告、原文树、队列), ../useWikiIngestSubscription (POS: ingest SSE 快照)
 * [OUTPUT] useWikiOverviewData: 总览与队列共用的知识库状态: 统计、健康报告、原文树、编译运行与 ingest 实时快照, 及其重新加载动作和由它们派生的待处理计数
 * [POS] Wiki 面板的数据层: 范围变化或回到总览页时重新加载统计; ingest 快照要求刷新时重读统计与原文树, 编译队列排空时提示一次完成; 本地开发环境挂有供 E2E 注入统计与健康报告的桥。
 */

import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { apiRequest } from '@/lib/api';
import {
  buildWikiApiPath,
  wikiService,
  type CompileRunStatus,
  type TreeNode,
  type WikiHealthReport,
} from '@/services/wikiService';
import { useWikiIngestSubscription } from '../useWikiIngestSubscription';
import type { WikiStats } from './types';

export function useWikiOverviewData(agentScopeId: string | null, activeTab: string) {
  const t = useTranslations('settings.wiki');
  const [stats, setStats] = useState<WikiStats | null>(null);
  const [healthReport, setHealthReport] = useState<WikiHealthReport | null>(null);
  const [healthReportExpanded, setHealthReportExpanded] = useState(false);
  const [isLoadingHealthReport, setIsLoadingHealthReport] = useState(false);
  const [healthReportLoadError, setHealthReportLoadError] = useState(false);
  const [rawTreeData, setRawTreeData] = useState<TreeNode[]>([]);
  const [treeSyncNonce, setTreeSyncNonce] = useState(0);
  const [isLoadingRawTree, setIsLoadingRawTree] = useState(false);
  const [compileRun, setCompileRun] = useState<CompileRunStatus | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(false);

  const loadHealthReport = useCallback(async () => {
    setIsLoadingHealthReport(true);
    setHealthReportLoadError(false);
    const tryE2eFetch = async (): Promise<boolean> => {
      if (typeof window === 'undefined' || sessionStorage.getItem('e2e_warm_platform_readiness') !== 'true') {
        return false;
      }
      try {
        const response = await fetch(buildWikiApiPath('/wiki/health-report', agentScopeId), { cache: 'no-store' });
        if (!response.ok) {
          return false;
        }
        const payload = (await response.json()) as WikiHealthReport | { data?: WikiHealthReport };
        const resolved =
          payload && typeof payload === 'object' && 'data' in payload && payload.data
            ? payload.data
            : (payload as WikiHealthReport);
        setHealthReport(resolved);
        if (resolved.open_actions_count > 0) {
          setHealthReportExpanded(true);
        }
        return true;
      } catch (fallbackError) {
        console.warn('Wiki health report E2E fallback failed:', fallbackError);
        return false;
      }
    };

    if (await tryE2eFetch()) {
      setIsLoadingHealthReport(false);
      return;
    }

    try {
      const report = await wikiService.getHealthReport(agentScopeId);
      setHealthReport(report);
      if (report.open_actions_count > 0) {
        setHealthReportExpanded(true);
      }
    } catch (error) {
      console.error('Failed to load wiki health report:', error);
      if (await tryE2eFetch()) {
        return;
      }
      setHealthReportLoadError(true);
    } finally {
      setIsLoadingHealthReport(false);
    }
  }, [agentScopeId]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }
    const host = window.location.hostname;
    if (host !== '127.0.0.1' && host !== 'localhost') {
      return undefined;
    }

    const applyStats = (detail: WikiStats) => {
      setStats(detail);
      setIsLoadingStats(false);
    };
    const applyHealth = (detail: WikiHealthReport) => {
      setHealthReport(detail);
      setHealthReportExpanded(true);
      setHealthReportLoadError(false);
      setIsLoadingHealthReport(false);
    };

    const bridge = window.__MYRM_E2E_WIKI__;
    if (bridge?.registerHandlers) {
      bridge.registerHandlers({
        applyStats: (stats) => applyStats(stats as WikiStats),
        applyHealth: (health) => applyHealth(health as WikiHealthReport),
      });
    }

    const handler = (event: Event) => {
      const detail = (event as CustomEvent<WikiStats>).detail;
      if (!detail || typeof detail !== 'object') {
        return;
      }
      applyStats(detail);
      void loadHealthReport();
    };

    window.addEventListener('myrm-e2e-wiki-stats', handler as EventListener);
    const healthHandler = (event: Event) => {
      const detail = (event as CustomEvent<WikiHealthReport>).detail;
      if (!detail || typeof detail !== 'object') {
        return;
      }
      applyHealth(detail);
    };
    window.addEventListener('myrm-e2e-wiki-health-report', healthHandler as EventListener);
    return () => {
      bridge?.unregisterHandlers?.();
      window.removeEventListener('myrm-e2e-wiki-stats', handler as EventListener);
      window.removeEventListener('myrm-e2e-wiki-health-report', healthHandler as EventListener);
    };
  }, [loadHealthReport]);

  const loadStats = async () => {
    setIsLoadingStats(true);
    setIsLoadingRawTree(true);

    const tryE2eStatsFetch = async (): Promise<boolean> => {
      if (typeof window === 'undefined' || sessionStorage.getItem('e2e_warm_platform_readiness') !== 'true') {
        return false;
      }
      try {
        const response = await fetch(buildWikiApiPath('/wiki/stats', agentScopeId), { cache: 'no-store' });
        if (!response.ok) {
          return false;
        }
        const payload = (await response.json()) as WikiStats | { data?: WikiStats };
        const resolved =
          payload && typeof payload === 'object' && 'data' in payload && payload.data
            ? payload.data
            : (payload as WikiStats);
        setStats(resolved);
        void loadHealthReport();
        return true;
      } catch (fallbackError) {
        console.warn('Wiki stats E2E fallback failed:', fallbackError);
        return false;
      }
    };

    if (await tryE2eStatsFetch()) {
      setIsLoadingStats(false);
      try {
        const [rawTree, queueStatus] = await Promise.all([
          wikiService.getRawTree(agentScopeId),
          wikiService.getQueueStatus(agentScopeId),
        ]);
        setRawTreeData(rawTree);
        setCompileRun(queueStatus.compile_run ?? null);
      } catch (error) {
        console.warn('Failed to load wiki ingest trees:', error);
      } finally {
        setIsLoadingRawTree(false);
      }
      return;
    }

    try {
      const data = await apiRequest<WikiStats>(buildWikiApiPath('/wiki/stats', agentScopeId));
      setStats(data);
      void loadHealthReport();
    } catch (error) {
      console.error('Failed to load Wiki stats:', error);
      if (await tryE2eStatsFetch()) {
        setIsLoadingRawTree(false);
        return;
      }
      toast.error(t('errors.loadStatsFailed'));
    } finally {
      setIsLoadingStats(false);
    }

    try {
      const [rawTree, queueStatus] = await Promise.all([
        wikiService.getRawTree(agentScopeId),
        wikiService.getQueueStatus(agentScopeId),
      ]);
      setRawTreeData(rawTree);
      setCompileRun(queueStatus.compile_run ?? null);
    } catch (error) {
      console.warn('Failed to load wiki ingest trees:', error);
    } finally {
      setIsLoadingRawTree(false);
    }
  };

  const reloadStats = useEffectEvent(() => {
    void loadStats();
  });

  useEffect(() => {
    reloadStats();
  }, [agentScopeId]);

  const prevTabRef = useRef(activeTab);
  useEffect(() => {
    if (activeTab === 'overview' && prevTabRef.current !== 'overview') {
      reloadStats();
    }
    prevTabRef.current = activeTab;
  }, [activeTab]);

  const ingestActivityRef = useRef(false);
  // Set when this page handed a compile to the background worker; the first idle snapshot after it reports the end.
  const compileRequestedRef = useRef(false);
  const markCompileRequested = (requested: boolean) => {
    compileRequestedRef.current = requested;
  };
  const bumpTreeSync = useCallback(() => setTreeSyncNonce((value) => value + 1), []);
  const refreshIngestTreesSilently = useCallback(async () => {
    try {
      const rawTree = await wikiService.getRawTree(agentScopeId);
      setRawTreeData(rawTree);
      bumpTreeSync();
    } catch (error) {
      console.warn('Failed to refresh wiki ingest trees after SSE signal.', error);
    }
  }, [agentScopeId, bumpTreeSync]);

  const { connected: ingestLive, snapshot: ingestSnapshot } = useWikiIngestSubscription(agentScopeId, {
    onSnapshot: (snap) => {
      setCompileRun(snap.compile_run ?? null);
      if (typeof snap.synthesis_pending_count === 'number') {
        setStats((prev) => (prev ? { ...prev, synthesis_pending: snap.synthesis_pending_count } : prev));
      }
      if (snap.tree_sync_required) {
        void refreshIngestTreesSilently();
        void loadStats();
      } else if (snap.stats_refresh_required) {
        void loadStats();
      }
      const active = snap.stats.processing > 0 || snap.stats.pending > 0 || snap.compile_run?.state === 'paused';
      if (ingestActivityRef.current && !active) {
        void loadStats();
        if (compileRequestedRef.current) {
          compileRequestedRef.current = false;
          toast.success(t('success.compileFinished', { tab: t('tabs.pendingEdits') }));
        }
      }
      ingestActivityRef.current = active;
    },
  });

  const duplicateGroupsPending = stats?.dedup_stats?.duplicate_groups_pending ?? 0;
  const dedupBlocksCompile = stats?.dedup_stats?.blocks_compile ?? false;

  const synthesisPendingCount =
    (typeof ingestSnapshot?.synthesis_pending_count === 'number'
      ? ingestSnapshot.synthesis_pending_count
      : undefined) ??
    stats?.synthesis_pending ??
    0;

  return {
    stats,
    isLoadingStats,
    loadStats,
    healthReport,
    setHealthReport,
    healthReportExpanded,
    setHealthReportExpanded,
    isLoadingHealthReport,
    healthReportLoadError,
    loadHealthReport,
    rawTreeData,
    isLoadingRawTree,
    treeSyncNonce,
    bumpTreeSync,
    refreshIngestTreesSilently,
    compileRun,
    setCompileRun,
    markCompileRequested,
    ingestLive,
    ingestSnapshot,
    duplicateGroupsPending,
    dedupBlocksCompile,
    synthesisPendingCount,
  };
}

export type WikiOverviewData = ReturnType<typeof useWikiOverviewData>;

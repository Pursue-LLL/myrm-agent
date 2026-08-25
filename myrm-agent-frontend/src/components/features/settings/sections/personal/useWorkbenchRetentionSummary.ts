'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';
import { getGrowthDashboard, type GrowthSnapshot } from '@/services/statistics';
import { listCronJobs } from '@/services/cron';
import { isLocalMode, isTauriRuntime, isSandbox, type DeployMode, getDeployMode } from '@/lib/deploy-mode';

export interface WikiStatsData {
  total_concepts: number;
  total_articles: number;
  total_raw_files: number;
  wiki_path: string;
}

export interface WorkspaceRuleItem {
  path: string;
  source: string;
  char_count: number;
  truncated: boolean;
  content: string;
}

export interface WorkspaceRulesData {
  rules: WorkspaceRuleItem[];
  total_chars: number;
  workspace_root: string;
}

export interface SubdirUsage {
  name: string;
  bytes: number;
}

export interface StorageInfoData {
  data_dir: string;
  disk_total_bytes: number;
  disk_used_bytes: number;
  disk_free_bytes: number;
  subdirs: SubdirUsage[];
}

export interface WorkbenchRetentionSummary {
  // Wiki
  wikiConcepts: number;
  wikiArticles: number;
  wikiRawFiles: number;
  wikiStatus: 'ok' | 'unavailable';

  // Memory
  totalMemories: number;
  memoryHealthScore: number;
  memoryStatus: 'ok' | 'unavailable';

  // Skills
  totalSkills: number;
  totalEvolutions: number;
  skillsStatus: 'ok' | 'unavailable';

  // Workspace rules
  totalRules: number;
  totalRuleChars: number;
  workspaceRoot: string;
  rulesStatus: 'ok' | 'unavailable';

  // Cron automation
  cronJobsCount: number;
  cronExecutions: number;
  cronStatus: 'ok' | 'unavailable';

  // Storage / Volume
  storageDataDir: string;
  storageUsedBytes: number;
  storageTotalBytes: number;
  storageFreeBytes: number;
  storageStatus: 'ok' | 'unavailable';

  // Runtime environment
  deployMode: DeployMode;
  isLocal: boolean;
  isTauri: boolean;
  isSandboxEnv: boolean;
}

interface UseWorkbenchRetentionSummaryResult {
  summary: WorkbenchRetentionSummary | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useWorkbenchRetentionSummary(): UseWorkbenchRetentionSummaryResult {
  const [summary, setSummary] = useState<WorkbenchRetentionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [wikiResult, growthResult, rulesResult, cronResult, storageResult] = await Promise.allSettled([
      apiRequest<WikiStatsData>('/wiki/stats'),
      getGrowthDashboard(30),
      apiRequest<WorkspaceRulesData>('/workspace/rules'),
      listCronJobs({ limit: 100 }),
      apiRequest<StorageInfoData>('/system/storage'),
    ]);

    const wiki = wikiResult.status === 'fulfilled' ? wikiResult.value : null;
    const growth = growthResult.status === 'fulfilled' ? growthResult.value : null;
    const rules = rulesResult.status === 'fulfilled' ? rulesResult.value : null;
    const cron = cronResult.status === 'fulfilled' ? cronResult.value : null;
    const storage = storageResult.status === 'fulfilled' ? storageResult.value : null;

    const deployMode = getDeployMode();
    const isLocal = isLocalMode();
    const isTauri = isTauriRuntime();
    const isSandboxEnv = isSandbox();

    const compiled: WorkbenchRetentionSummary = {
      // Wiki
      wikiConcepts: wiki?.total_concepts ?? 0,
      wikiArticles: wiki?.total_articles ?? 0,
      wikiRawFiles: wiki?.total_raw_files ?? 0,
      wikiStatus: wikiResult.status === 'fulfilled' ? 'ok' : 'unavailable',

      // Memory
      totalMemories: growth?.snapshot.total_memories ?? 0,
      memoryHealthScore: growth?.snapshot.memory_health_score ?? 100,
      memoryStatus: growthResult.status === 'fulfilled' ? 'ok' : 'unavailable',

      // Skills
      totalSkills: growth?.snapshot.total_skills ?? 0,
      totalEvolutions: growth?.snapshot.total_evolutions ?? 0,
      skillsStatus: growthResult.status === 'fulfilled' ? 'ok' : 'unavailable',

      // Workspace Rules
      totalRules: rules?.rules.length ?? 0,
      totalRuleChars: rules?.total_chars ?? 0,
      workspaceRoot: rules?.workspace_root ?? '',
      rulesStatus: rulesResult.status === 'fulfilled' ? 'ok' : 'unavailable',

      // Cron
      cronJobsCount: cron?.items?.length ?? 0,
      cronExecutions: growth?.weekly_summary.cron_executions ?? 0,
      cronStatus: cronResult.status === 'fulfilled' ? 'ok' : 'unavailable',

      // Storage
      storageDataDir: storage?.data_dir ?? '',
      storageUsedBytes: storage?.disk_used_bytes ?? 0,
      storageTotalBytes: storage?.disk_total_bytes ?? 0,
      storageFreeBytes: storage?.disk_free_bytes ?? 0,
      storageStatus: storageResult.status === 'fulfilled' ? 'ok' : 'unavailable',

      deployMode,
      isLocal,
      isTauri,
      isSandboxEnv,
    };

    setSummary(compiled);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return {
    summary,
    loading,
    error,
    reload: loadData,
  };
}

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useTranslations, useLocale } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { IconBook, IconGlow, IconWrench, IconDatabase, IconExplore } from '@/components/features/icons/PremiumIcons';
import { Textarea } from '@/components/primitives/textarea';
import { ApiError, apiRequest } from '@/lib/api';
import { isTauri } from '@/lib/utils/clipboardUtils';
import {
  wikiService,
  buildWikiApiPath,
  buildWikiAssetUrl,
  type CompileRunStatus,
  type ImportResultResponse,
  type ObsidianImportResultResponse,
  type WikiImportConflictOptions,
  type WikiRetrievalTrace,
  type WikiSourceLevel,
  type WikiSourceSnippet,
  type WikiHealthReport,
  type TreeNode,
} from '@/services/wikiService';
import { formatClaimConfidence } from '@/lib/wiki/claimStatusDisplay';
import { recordEvidenceSurface, recordWikiQueryAttempt, recordWikiQuerySubmitted } from '@/services/wiki/evidenceMetrics';
import { resolveWikiSectionLabel } from '@/services/wiki/sectionLabels';
import { listAgents, type AgentListItem } from '@/services/agent';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import SourceChunkDrawer from '@/components/features/message-box/SourceChunkDrawer';
import { WikiConceptsList } from './WikiConceptsList';
import { WikiImportConflictDialog } from './wiki/WikiImportConflictDialog';
import { WikiImportSecurityDialog } from './wiki/WikiImportSecurityDialog';
import { WikiRawSourceTree } from './wiki/WikiRawSourceTree';
import { WikiPendingEdits } from './WikiPendingEdits';
import { WikiDuplicateReviewPanel } from './WikiDuplicateReviewPanel';
import { WikiHealthIssuesSection } from './WikiHealthIssuesSection';
import { WikiIgnorePanel } from './WikiIgnorePanel';
import { WikiQueuePanel } from './WikiQueuePanel';
import { WikiCompilePhaseBar } from './WikiCompilePhaseBar';
import { WikiAgentScopeProvider } from './WikiAgentScopeContext';
import { useWikiIngestSubscription } from './useWikiIngestSubscription';
import WikiSourceSyncPanel from './WikiSourceSyncPanel';
import SecondBrainSetupCard from './SecondBrainSetupCard';
import { ObsidianVaultActions } from './ObsidianVaultActions';
import { consumeMigrationObsidianVaultImport } from '@/lib/migrationChatHandoff';
import { healthReportFromMaintainResponse, resolveHealthIssueNavigationTarget } from './wiki/wikiSectionUtils';

interface WikiStats {
  total_concepts: number;
  total_articles: number;
  total_raw_files: number;
  wiki_path: string;
  vault_ready: boolean;
  legacy_migrated: boolean;
  cognitive_index_ready: boolean;
  cognitive_log_entries: number;
  cognitive_hot_updated_at: string | null;
  structural_issues?: {
    broken_links: number;
    invalid_frontmatter_types: number;
    provenance_gaps: number;
    scanned_concepts: number;
  };
  asset_index?: {
    indexed: number;
    pending: number;
    failed: number;
    total_files: number;
    enabled: boolean;
  };
  synthesis_pending?: number;
  obsidian_launch_available?: boolean;
  vault_git_enabled?: boolean;
  vault_git_initialized?: boolean;
  vault_git_last_commit?: string | null;
  maintain_state?: {
    last_run_at: string | null;
    last_mode: string | null;
    last_issues_found: number;
    last_issues_fixed: number;
    last_connections_discovered: number;
    last_duration_ms: number;
    last_skipped_reason: string | null;
  };
  dedup_stats?: {
    duplicate_groups_pending: number;
    compile_jobs_prevented: number;
    eligible_raw_count: number;
    excluded_raw_count: number;
    trashed_raw_count: number;
    blocks_compile: boolean;
  };
}

function formatCognitiveUpdatedAt(iso: string | null | undefined, locale: string): string {
  if (!iso) {
    return '';
  }
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) {
    return iso;
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

function maintainSkippedBadgeLabel(
  reason: string,
  translate: (key: string) => string,
): string {
  if (reason === 'compile_in_progress') {
    return translate('stats.lastMaintainSkippedCompile');
  }
  if (reason === 'no_llm_configured') {
    return translate('stats.lastMaintainSkippedNoModel');
  }
  return translate('stats.lastMaintainSkipped');
}

function normalizeWikiLevel(level: string | undefined): WikiSourceLevel | undefined {
  if (level === 'L0' || level === 'L1' || level === 'L2') {
    return level;
  }
  return undefined;
}

const WIKI_TABS = ['overview', 'concepts', 'pendingEdits', 'duplicateReview', 'queue'] as const;
type WikiTab = (typeof WIKI_TABS)[number];

function isWikiTab(value: string): value is WikiTab {
  return (WIKI_TABS as readonly string[]).includes(value);
}

interface PendingImportRetry {
  kind: 'folder' | 'zip' | 'obsidian-folder' | 'obsidian-zip';
  folderPath?: string;
  zipFile?: File;
}

export function WikiSection() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const locale = useLocale();
  const agentScopeId = searchParams.get('agentId');
  const evidenceContextKey = agentScopeId ? `agent:${agentScopeId}` : 'agent:default';
  const t = useTranslations('settings.wiki');
  const tSources = useTranslations('MessageSources');
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [queryMode, setQueryMode] = useState<'auto' | 'raw_claim'>('auto');
  const [maintainMode, setMaintainMode] = useState<'structural' | 'full'>('structural');
  const [answer, setAnswer] = useState('');
  const [relatedArticles, setRelatedArticles] = useState<string[]>([]);
  const [sourceSnippets, setSourceSnippets] = useState<WikiSourceSnippet[]>([]);
  const [queryConfidence, setQueryConfidence] = useState<number | null>(null);
  const [retrievalTrace, setRetrievalTrace] = useState<WikiRetrievalTrace | null>(null);
  const [snippetDrawerState, setSnippetDrawerState] = useState<{
    open: boolean;
    title: string;
    section?: string;
    snippet: string;
    level?: WikiSourceLevel;
    snapshotStatus?: WikiSourceSnippet['snapshot_status'];
    claimStatus?: WikiSourceSnippet['claim_status'];
    claimConfidence?: WikiSourceSnippet['claim_confidence'];
    claimText?: WikiSourceSnippet['claim_text'];
    resourceUri?: string;
    supersededFromUri?: string;
    thumbnailUrl?: string | null;
  }>({ open: false, title: '', snippet: '' });
  const [stats, setStats] = useState<WikiStats | null>(null);
  const [healthReport, setHealthReport] = useState<WikiHealthReport | null>(null);
  const [healthReportExpanded, setHealthReportExpanded] = useState(false);
  const [isLoadingHealthReport, setIsLoadingHealthReport] = useState(false);
  const [healthReportLoadError, setHealthReportLoadError] = useState(false);
  const [rawTreeData, setRawTreeData] = useState<TreeNode[]>([]);
  const [treeSyncNonce, setTreeSyncNonce] = useState(0);
  const [isLoadingRawTree, setIsLoadingRawTree] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [isCompiling, setIsCompiling] = useState(false);
  const [compileRun, setCompileRun] = useState<CompileRunStatus | null>(null);
  const [isResumingCompile, setIsResumingCompile] = useState(false);
  const [isMaintaining, setIsMaintaining] = useState(false);
  const [isRepairingTypes, setIsRepairingTypes] = useState(false);
  const [isRepairingPublication, setIsRepairingPublication] = useState(false);
  const [isReindexingVectors, setIsReindexingVectors] = useState(false);
  const [reindexErrors, setReindexErrors] = useState<string[]>([]);
  const [isLoadingStats, setIsLoadingStats] = useState(false);
  const [purpose, setPurpose] = useState('');
  const [purposeDraft, setPurposeDraft] = useState('');
  const [isLoadingPurpose, setIsLoadingPurpose] = useState(false);
  const [isSavingPurpose, setIsSavingPurpose] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isImportingObsidian, setIsImportingObsidian] = useState(false);
  const [scopeRevision, setScopeRevision] = useState(0);
  const [activeTab, setActiveTab] = useState('overview');
  const [pendingEditsInitialFilter, setPendingEditsInitialFilter] = useState<'all' | 'concepts' | 'synthesis'>('all');
  const zipInputRef = useRef<HTMLInputElement>(null);
  const obsidianZipRef = useRef<HTMLInputElement>(null);
  const webFolderInputRef = useRef<HTMLInputElement>(null);
  const [importConflictOpen, setImportConflictOpen] = useState(false);
  const [importConflictPaths, setImportConflictPaths] = useState<string[]>([]);
  const [importSecurityOpen, setImportSecurityOpen] = useState(false);
  const [importSecurityBlockedPaths, setImportSecurityBlockedPaths] = useState<string[]>([]);
  const [importSecurityRedactedPaths, setImportSecurityRedactedPaths] = useState<string[]>([]);
  const [pendingImportRetry, setPendingImportRetry] = useState<PendingImportRetry | null>(null);

  const syncWikiTabToUrl = useCallback(
    (tab: WikiTab) => {
      const params = new URLSearchParams(searchParams.toString());
      if (tab === 'overview') {
        params.delete('wikiTab');
      } else {
        params.set('wikiTab', tab);
      }
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [searchParams, router, pathname],
  );

  const handleWikiTabChange = useCallback(
    (tab: string) => {
      if (!isWikiTab(tab)) {
        return;
      }
      setActiveTab(tab);
      syncWikiTabToUrl(tab);
    },
    [syncWikiTabToUrl],
  );

  useEffect(() => {
    const tab = searchParams.get('wikiTab');
    if (tab && isWikiTab(tab)) {
      setActiveTab(tab);
      return;
    }
    if (!tab) {
      setActiveTab('overview');
    }
  }, [searchParams]);

  const rawPathFromUrl = searchParams.get('rawPath');
  const conceptPathFromUrl = searchParams.get('conceptPath');

  useEffect(() => {
    const focus = searchParams.get('focus');
    if (focus === 'wikiignore') {
      document.getElementById('wiki-wikiignore-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [searchParams]);

  const isTauriEnv = isTauri();

  const scopeLabel = agentScopeId
    ? getBuiltinAgentName(
        agentScopeId,
        agents.find((agent) => agent.id === agentScopeId)?.name ?? agentScopeId,
        locale,
      )
    : t('agentScopeDefault');

  const nudgeObsidianVaultCard = useCallback(() => {
    toast.message(t('obsidianVault.postWorkflowHint'), {
      action: {
        label: t('obsidianVault.postWorkflowAction'),
        onClick: () => {
          const params = new URLSearchParams({ tab: 'graph' });
          if (agentScopeId) {
            params.set('agentId', agentScopeId);
          }
          router.push(`/library?${params.toString()}`);
        },
      },
    });
  }, [agentScopeId, router, t]);

  const goToKnowledgeGraph = useCallback(() => {
    const params = new URLSearchParams({ tab: 'graph' });
    if (agentScopeId) {
      params.set('agentId', agentScopeId);
    }
    router.push(`/library?${params.toString()}`);
  }, [agentScopeId, router]);

  const showObsidianResult = (result: ObsidianImportResultResponse) => {
    toast.success(
      t('import.obsidianResult', {
        processed: result.files_processed,
        tags: result.tags_extracted,
        images: result.images_copied,
        skipped: result.files_skipped + (result.files_skipped_conflict ?? 0),
      }),
    );
    nudgeObsidianVaultCard();
  };

  const finishImportResult = async (
    result: ImportResultResponse | ObsidianImportResultResponse,
    retry: PendingImportRetry | null,
    toastMode: 'default' | 'obsidian' = 'default',
  ) => {
    if (result.success) {
      if (toastMode === 'obsidian') {
        showObsidianResult(result as ObsidianImportResultResponse);
      } else {
        toast.success(result.message);
      }
      toast.message(t('import.dedupScanStarted'));
      handleWikiTabChange('duplicateReview');
      await loadStats();
      const blocked = result.security_blocked_paths ?? [];
      const redacted = result.security_redacted_paths ?? [];
      if (blocked.length > 0 || redacted.length > 0) {
        setImportSecurityBlockedPaths(blocked);
        setImportSecurityRedactedPaths(redacted);
        setImportSecurityOpen(true);
      }
      const conflicts = result.conflict_paths ?? [];
      if (conflicts.length > 0 && retry) {
        setImportConflictPaths(conflicts);
        setPendingImportRetry(retry);
        setImportConflictOpen(true);
      }
    } else {
      toast.error(result.message);
    }
  };

  const migrationVaultHandoffRef = useRef(false);
  useEffect(() => {
    if (migrationVaultHandoffRef.current || typeof window === 'undefined') {
      return;
    }
    if (!window.location.hash.includes('wiki-obsidian-import')) {
      return;
    }
    const handoff = consumeMigrationObsidianVaultImport(agentScopeId ?? undefined);
    if (!handoff?.vaultPath) {
      return;
    }
    migrationVaultHandoffRef.current = true;
    document.getElementById('wiki-obsidian-import')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    toast.message(t('import.migrationVaultHandoff', { path: handoff.vaultPath }));
    setIsImportingObsidian(true);
    void wikiService
      .importObsidianFolder(handoff.vaultPath, true, agentScopeId)
      .then(async (result) => {
        await finishImportResult(
          result,
          { kind: 'obsidian-folder', folderPath: handoff.vaultPath },
          'obsidian',
        );
      })
      .catch(() => {
        toast.error(t('import.migrationVaultHandoffFailed'));
      })
      .finally(() => {
        setIsImportingObsidian(false);
      });
  }, [agentScopeId, finishImportResult, t]);

  const retryImportWithSupersede = async (reason: string) => {
    if (!pendingImportRetry) {
      setImportConflictOpen(false);
      return;
    }

    const conflictOptions: WikiImportConflictOptions = {
      onConflict: 'supersede',
      supersedeReason: reason,
    };

    setImportConflictOpen(false);
    setImportConflictPaths([]);
    const retry = pendingImportRetry;
    setPendingImportRetry(null);

    try {
      if (retry.kind === 'folder' && retry.folderPath) {
        setIsImporting(true);
        const result = await wikiService.importFolder(
          retry.folderPath,
          ['.md', '.txt', '.org'],
          true,
          agentScopeId,
          conflictOptions,
        );
        await finishImportResult(result, null);
      } else if (retry.kind === 'zip' && retry.zipFile) {
        setIsImporting(true);
        const result = await wikiService.importZip(
          retry.zipFile,
          '.md,.txt,.org',
          true,
          agentScopeId,
          conflictOptions,
        );
        await finishImportResult(result, null);
      } else if (retry.kind === 'obsidian-folder' && retry.folderPath) {
        setIsImportingObsidian(true);
        const result = await wikiService.importObsidianFolder(
          retry.folderPath,
          true,
          agentScopeId,
          conflictOptions,
        );
        await finishImportResult(result, null);
      } else if (retry.kind === 'obsidian-zip' && retry.zipFile) {
        setIsImportingObsidian(true);
        const result = await wikiService.importObsidianZip(retry.zipFile, true, agentScopeId, conflictOptions);
        await finishImportResult(result, null);
      }
    } catch (error) {
      console.error('Import supersede retry failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      setIsImportingObsidian(false);
    }
  };

  const handleImportFolder = async () => {
    if (isTauriEnv) {
      try {
        const { open } = await import('@tauri-apps/plugin-dialog');
        const selected = await open({ directory: true, multiple: false, title: t('import.selectFolder') });
        if (!selected) {return;}

        setIsImporting(true);
        const folderPath = selected as string;
        const result = await wikiService.importFolder(folderPath, ['.md', '.txt', '.org'], true, agentScopeId);
        await finishImportResult(result, { kind: 'folder', folderPath });
      } catch (error) {
        console.error('Folder import failed:', error);
        toast.error(t('errors.importFailed'));
      } finally {
        setIsImporting(false);
      }
    } else {
      webFolderInputRef.current?.click();
    }
  };

  const handleWebFolderSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) {return;}

    setIsImporting(true);
    try {
      const { default: JSZip } = await import('jszip');
      const zip = new JSZip();

      const validExtensions = new Set(['.md', '.txt', '.org']);
      let addedCount = 0;

      for (const file of Array.from(files)) {
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (!validExtensions.has(ext)) {continue;}

        const content = await file.arrayBuffer();
        const relativePath = file.webkitRelativePath || file.name;
        zip.file(relativePath, content);
        addedCount++;
      }

      if (addedCount === 0) {
        toast.error(t('import.noValidFiles'));
        return;
      }

      const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
      const zipFile = new File([blob], 'folder-import.zip', { type: 'application/zip' });

      const result = await wikiService.importZip(zipFile, '.md,.txt,.org', true, agentScopeId);
      await finishImportResult(result, { kind: 'zip', zipFile });
    } catch (error) {
      console.error('Web folder import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      if (webFolderInputRef.current) {webFolderInputRef.current.value = '';}
    }
  };

  const handleImportZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {return;}

    setIsImporting(true);
    try {
      const result = await wikiService.importZip(file, '.md,.txt,.org', true, agentScopeId);
      await finishImportResult(result, { kind: 'zip', zipFile: file });
    } catch (error) {
      console.error('ZIP import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      if (zipInputRef.current) {zipInputRef.current.value = '';}
    }
  };

  const handleImportObsidianFolder = async () => {
    if (!isTauriEnv) {return;}
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false, title: t('import.selectObsidianVault') });
      if (!selected) {return;}

      setIsImportingObsidian(true);
      const vaultPath = selected as string;
      const result = await wikiService.importObsidianFolder(vaultPath, true, agentScopeId);
      await finishImportResult(result, { kind: 'obsidian-folder', folderPath: vaultPath }, 'obsidian');
    } catch (error) {
      console.error('Obsidian folder import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImportingObsidian(false);
    }
  };

  const handleImportObsidianZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {return;}

    setIsImportingObsidian(true);
    try {
      const result = await wikiService.importObsidianZip(file, true, agentScopeId);
      await finishImportResult(result, { kind: 'obsidian-zip', zipFile: file }, 'obsidian');
    } catch (error) {
      console.error('Obsidian ZIP import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImportingObsidian(false);
      if (obsidianZipRef.current) {obsidianZipRef.current.value = '';}
    }
  };

  useEffect(() => {
    setAgentsLoading(true);
    listAgents(1, 100)
      .then((res) => setAgents(res.items))
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false));
  }, []);

  const handleAgentScopeChange = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === 'default') {
      params.delete('agentId');
    } else {
      params.set('agentId', value);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  useEffect(() => {
    setScopeRevision((revision) => revision + 1);
    void loadPurpose();
    void loadStats();
    setAnswer('');
    setRelatedArticles([]);
    setSourceSnippets([]);
  }, [agentScopeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const prevTabRef = useRef(activeTab);
  useEffect(() => {
    if (activeTab === 'overview' && prevTabRef.current !== 'overview') {
      void loadStats();
    }
    prevTabRef.current = activeTab;
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadPurpose = async () => {
    setIsLoadingPurpose(true);
    try {
      const data = await apiRequest<{ purpose: string }>(buildWikiApiPath('/wiki/purpose', agentScopeId));
      setPurpose(data.purpose);
      setPurposeDraft(data.purpose);
    } catch (error) {
      console.error('Failed to load purpose:', error);
    } finally {
      setIsLoadingPurpose(false);
    }
  };

  const handleSavePurpose = async () => {
    setIsSavingPurpose(true);
    try {
      await apiRequest(buildWikiApiPath('/wiki/purpose', agentScopeId), {
        method: 'PUT',
        body: JSON.stringify({ purpose: purposeDraft }),
      });
      setPurpose(purposeDraft);
      toast.success(t('success.purposeSaved'));
    } catch (error) {
      console.error('Failed to save purpose:', error);
      toast.error(t('errors.purposeSaveFailed'));
    } finally {
      setIsSavingPurpose(false);
    }
  };

  const loadHealthReport = useCallback(async () => {
    setIsLoadingHealthReport(true);
    setHealthReportLoadError(false);
    const tryE2eFetch = async (): Promise<boolean> => {
      if (
        typeof window === 'undefined' ||
        sessionStorage.getItem('e2e_warm_platform_readiness') !== 'true'
      ) {
        return false;
      }
      try {
        const response = await fetch(
          buildWikiApiPath('/wiki/health-report', agentScopeId),
          { cache: 'no-store' },
        );
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
        setIsLoadingHealthReport(false);
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

  const navigateToHealthIssue = useCallback(
    (location: string) => {
      const target = resolveHealthIssueNavigationTarget(location);
      const params = new URLSearchParams(searchParams.toString());
      params.delete('rawPath');
      params.delete('conceptPath');
      if (target.kind === 'raw') {
        params.delete('wikiTab');
        params.set('rawPath', target.path);
        setActiveTab('overview');
      } else {
        params.set('wikiTab', 'concepts');
        params.set('conceptPath', target.path);
        setActiveTab('concepts');
      }
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const loadStats = async () => {
    setIsLoadingStats(true);
    setIsLoadingRawTree(true);

    const tryE2eStatsFetch = async (): Promise<boolean> => {
      if (
        typeof window === 'undefined' ||
        sessionStorage.getItem('e2e_warm_platform_readiness') !== 'true'
      ) {
        return false;
      }
      try {
        const response = await fetch(
          buildWikiApiPath('/wiki/stats', agentScopeId),
          { cache: 'no-store' },
        );
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
      setIsLoadingRawTree(false);
      return;
    }

    try {
      const data = await apiRequest<WikiStats>(buildWikiApiPath('/wiki/stats', agentScopeId));
      setStats(data);
      void loadHealthReport();
    } catch (error) {
      console.error('Failed to load Wiki stats:', error);
      if (await tryE2eStatsFetch()) {
        setIsLoadingStats(false);
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

  const ingestActivityRef = useRef(false);
  const refreshIngestTreesSilently = useCallback(async () => {
    try {
      const rawTree = await wikiService.getRawTree(agentScopeId);
      setRawTreeData(rawTree);
      setTreeSyncNonce((nonce) => nonce + 1);
    } catch (error) {
      console.warn('Failed to refresh wiki ingest trees after SSE signal.', error);
    }
  }, [agentScopeId]);

  const { connected: ingestLive, snapshot: ingestSnapshot } = useWikiIngestSubscription(agentScopeId, {
    onSnapshot: (snap) => {
      setCompileRun(snap.compile_run ?? null);
      if (typeof snap.synthesis_pending_count === 'number') {
        setStats((prev) =>
          prev ? { ...prev, synthesis_pending: snap.synthesis_pending_count } : prev,
        );
      }
      if (snap.tree_sync_required) {
        void refreshIngestTreesSilently();
        void loadStats();
      } else if (snap.stats_refresh_required) {
        void loadStats();
      }
      const active =
        snap.stats.processing > 0 ||
        snap.stats.pending > 0 ||
        snap.compile_run?.state === 'paused';
      if (ingestActivityRef.current && !active) {
        void loadStats();
      }
      ingestActivityRef.current = active;
    },
  });

  const isWikiCompileBusy =
    isCompiling ||
    compileRun?.state === 'running' ||
    (ingestSnapshot?.stats.processing ?? 0) > 0;

  const handleOpenSynthesisPending = () => {
    setPendingEditsInitialFilter('synthesis');
    handleWikiTabChange('pendingEdits');
  };

  const handleOpenDuplicateReview = () => {
    handleWikiTabChange('duplicateReview');
  };

  const duplicateGroupsPending = stats?.dedup_stats?.duplicate_groups_pending ?? 0;
  const dedupBlocksCompile = stats?.dedup_stats?.blocks_compile ?? false;

  const synthesisPendingCount =
    (typeof ingestSnapshot?.synthesis_pending_count === 'number'
      ? ingestSnapshot.synthesis_pending_count
      : undefined) ??
    stats?.synthesis_pending ??
    0;

  const handleQuery = async () => {
    if (!query.trim()) {
      toast.error(t('errors.emptyQuery'));
      return;
    }

    recordWikiQueryAttempt('settings', evidenceContextKey);
    setIsQuerying(true);
    setAnswer('');
    setRelatedArticles([]);
    setSourceSnippets([]);
    setQueryConfidence(null);
    setRetrievalTrace(null);

    try {
      const data = await wikiService.queryWiki(query, queryMode, agentScopeId);

      setAnswer(data.answer);
      setRelatedArticles(data.related_articles || []);
      setSourceSnippets(data.source_snippets || []);
      setQueryConfidence(typeof data.confidence_score === 'number' ? data.confidence_score : null);
      setRetrievalTrace(data.retrieval_trace ?? null);
      recordWikiQuerySubmitted('settings', evidenceContextKey);
      recordEvidenceSurface('settings', data.source_snippets?.length ?? 0, evidenceContextKey);
      toast.success(t('success.queryComplete'));
    } catch (error) {
      console.error('Query failed:', error);
      toast.error(t('errors.queryFailed'));
    } finally {
      setIsQuerying(false);
    }
  };

  const handleCompile = async () => {
    setIsCompiling(true);
    try {
      const result = await wikiService.compileWiki(agentScopeId);
      setCompileRun(result.compile_run ?? null);
      if (result.compile_run?.state === 'paused') {
        toast.warning(result.compile_run.pause_reason || t('compileRun.pausedDefaultReason'));
        handleWikiTabChange('queue');
      } else {
        const synthesisCount = result.synthesis_pending ?? 0;
        toast.success(
          synthesisCount > 0
            ? t('success.compileSummaryWithSynthesis', {
                published: result.articles_published,
                pending: result.articles_pending,
                blocked: result.articles_blocked,
                synthesis: synthesisCount,
              })
            : t('success.compileSummary', {
                published: result.articles_published,
                pending: result.articles_pending,
                blocked: result.articles_blocked,
              }),
        );
        if (result.articles_pending > 0 || synthesisCount > 0) {
          setPendingEditsInitialFilter(synthesisCount > 0 ? 'synthesis' : 'all');
          handleWikiTabChange('pendingEdits');
        }
      }
      await loadStats();
    } catch (error) {
      console.error('Compile failed:', error);
      if (error instanceof ApiError && error.code === 409) {
        toast.error(t('errors.compileBlockedByDedup'));
        handleWikiTabChange('duplicateReview');
        return;
      }
      toast.error(t('errors.compileFailed'));
    } finally {
      setIsCompiling(false);
    }
  };

  const handleResumeCompile = async () => {
    setIsResumingCompile(true);
    try {
      await wikiService.resumeCompileCircuit(agentScopeId);
      toast.success(t('compileRun.resumeSuccess'));
      await loadStats();
    } catch (error) {
      console.error('Resume compile failed:', error);
      toast.error(t('compileRun.resumeFailed'));
    } finally {
      setIsResumingCompile(false);
    }
  };

  const handleMaintain = async () => {
    setIsMaintaining(true);
    try {
      const result = await wikiService.maintainWiki(maintainMode, agentScopeId);
      const removed = result.raw_security_removed ?? 0;
      if (removed > 0) {
        const pathsJoined = (result.raw_security_removed_paths ?? []).join(', ');
        const displayPaths =
          pathsJoined.length > 120 ? `${pathsJoined.slice(0, 117)}...` : pathsJoined;
        toast.success(
          t('success.maintainRemovedSensitive', {
            count: removed,
            paths: displayPaths,
          }),
        );
      } else {
        const openActions = result.open_actions_count ?? 0;
        const fixed = result.issues_fixed ?? 0;
        if (openActions > 0) {
          toast.message(
            t('healthReport.maintainToastOpen', { open: openActions, fixed }),
          );
        } else if (fixed > 0) {
          toast.success(t('success.maintainSummary', { found: result.issues_found, fixed }));
        } else {
          toast.success(t('success.maintainComplete'));
        }
      }
      setHealthReportExpanded(true);
      await loadStats();
      setHealthReport((prev) =>
        healthReportFromMaintainResponse(result, maintainMode, {
          duplicate_groups_pending: prev?.duplicate_groups_pending ?? 0,
          synthesis_pending: prev?.synthesis_pending ?? 0,
        }),
      );
      setTreeSyncNonce((value) => value + 1);
    } catch (error) {
      console.error('Maintain failed:', error);
      if (error instanceof ApiError && error.code === 409) {
        toast.error(t('errors.maintainCompileBusy'));
      } else {
        toast.error(t('errors.maintainFailed'));
      }
    } finally {
      setIsMaintaining(false);
    }
  };

  const handleRepairPageTypes = async () => {
    setIsRepairingTypes(true);
    try {
      const result = await wikiService.repairPageTypes(agentScopeId);
      if (result.success) {
        toast.success(t('success.repairTypesComplete', { count: result.files_repaired }));
      } else {
        toast.warning(result.message);
      }
      await loadStats();
    } catch (error) {
      console.error('Repair page types failed:', error);
      toast.error(t('errors.repairTypesFailed'));
    } finally {
      setIsRepairingTypes(false);
    }
  };

  const handleRepairPublication = async () => {
    setIsRepairingPublication(true);
    try {
      const result = await wikiService.repairPublication(agentScopeId);
      if (result.success) {
        const skippedDrafts = result.files_skipped_intentional_drafts ?? 0;
        toast.success(
          skippedDrafts > 0
            ? t('success.repairPublicationCompleteWithSkips', {
                repaired: result.files_repaired,
                reindexed: result.reindexed,
                skippedDrafts,
              })
            : t('success.repairPublicationComplete', {
                repaired: result.files_repaired,
                reindexed: result.reindexed,
              }),
        );
      } else {
        toast.warning(result.message);
      }
      await loadStats();
    } catch (error) {
      console.error('Repair publication failed:', error);
      toast.error(t('errors.repairPublicationFailed'));
    } finally {
      setIsRepairingPublication(false);
    }
  };

  const handleReindexVectors = async () => {
    setIsReindexingVectors(true);
    setReindexErrors([]);
    try {
      const result = await wikiService.reindexVectors(agentScopeId);
      setReindexErrors(result.errors ?? []);
      if (result.success) {
        toast.success(
          t('success.reindexVectorsComplete', {
            concepts: result.concepts_reindexed,
            sidecars: result.sidecars_reindexed,
            assets: result.assets_indexed,
          }),
        );
      } else {
        toast.warning(result.message);
      }
      await loadStats();
      setTreeSyncNonce((value) => value + 1);
    } catch (error) {
      console.error('Reindex wiki vectors failed:', error);
      toast.error(t('errors.reindexVectorsFailed'));
    } finally {
      setIsReindexingVectors(false);
    }
  };

  return (
    <WikiAgentScopeProvider
      agentScopeId={agentScopeId}
      scopeRevision={scopeRevision}
      scopeLabel={scopeLabel}
    >
      <div className="space-y-6" data-testid="wiki-settings-shell">
      <div>
        <h2 className="text-2xl font-semibold mb-2">{t('title')}</h2>
        <p className="text-muted-foreground">{t('description')}</p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
            <span className="text-sm font-medium text-foreground">{t('agentScopeLabel')}</span>
            <Select
              value={agentScopeId ?? 'default'}
              onValueChange={handleAgentScopeChange}
              disabled={agentsLoading}
            >
              <SelectTrigger className="w-full sm:w-72">
                <SelectValue placeholder={agentsLoading ? t('loading') : t('agentScopePlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">{t('agentScopeDefault')}</SelectItem>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {getBuiltinAgentName(agent.id, agent.name, locale)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-sm text-primary/80">
            {agentScopeId ? t('agentScopeNotice') : t('defaultScopeNotice')}
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={handleWikiTabChange} className="flex flex-col flex-1 min-h-0 space-y-6">
        <TabsList className="flex flex-wrap h-auto w-full bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 gap-1">
          <TabsTrigger value="overview">{t('tabs.overview')}</TabsTrigger>
          <TabsTrigger value="concepts">{t('tabs.concepts')}</TabsTrigger>
          <TabsTrigger value="pendingEdits">{t('tabs.pendingEdits')}</TabsTrigger>
          <TabsTrigger value="duplicateReview" data-testid="wiki-dedup-tab">
            {t('tabs.duplicateReview')}
          </TabsTrigger>
          <TabsTrigger value="queue">{t('tabs.queue')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <SecondBrainSetupCard
            onApplied={(agentId) => {
              void loadStats();
              const params = new URLSearchParams(searchParams.toString());
              params.set('agentId', agentId);
              router.replace(`${pathname}?${params.toString()}`);
            }}
            onGoToImport={() =>
              document.getElementById('wiki-obsidian-import')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }
            onGoToProviders={() => router.push('/settings/models')}
            onGoToDuplicateReview={handleOpenDuplicateReview}
            onGoToGraph={goToKnowledgeGraph}
          />

          <WikiSourceSyncPanel onGoToIntegrations={() => router.push('/settings/credentials')} />

          {/* Purpose / Direction */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconExplore className="w-5 h-5" />
                {t('purpose.title')}
              </CardTitle>
              <CardDescription>{t('purpose.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {isLoadingPurpose ? (
                <div className="text-center py-4 text-muted-foreground">{t('loading')}</div>
              ) : (
                <>
                  <Textarea
                    placeholder={t('purpose.placeholder')}
                    value={purposeDraft}
                    onChange={(e) => setPurposeDraft(e.target.value)}
                    rows={3}
                    className="resize-none"
                  />
                  <div className="flex justify-end gap-2">
                    {purposeDraft !== purpose && (
                      <Button variant="ghost" size="sm" onClick={() => setPurposeDraft(purpose)}>
                        {t('purpose.reset')}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={handleSavePurpose}
                      disabled={isSavingPurpose || purposeDraft === purpose}
                    >
                      {isSavingPurpose ? t('purpose.saving') : t('purpose.save')}
                    </Button>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Wiki Stats */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconDatabase className="w-5 h-5" />
                {t('stats.title')}
              </CardTitle>
              <CardDescription>{t('stats.description')}</CardDescription>
            </CardHeader>
            <CardContent>
              {!stats && !isLoadingStats && (
                <Button onClick={loadStats} variant="outline" data-testid="wiki-load-stats-btn">
                  {t('actions.loadStats')}
                </Button>
              )}

              {isLoadingStats && (
                <div
                  className="text-center py-4 text-muted-foreground"
                  data-testid="wiki-stats-loading"
                >
                  {t('loading')}
                </div>
              )}

              {stats && (
                <div className="space-y-4" data-testid="wiki-stats-panel">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span
                      className={
                        stats.vault_ready
                          ? 'inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-emerald-600 dark:text-emerald-400'
                          : 'inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400'
                      }
                    >
                      {stats.vault_ready ? t('stats.vaultReady') : t('stats.vaultNotReady')}
                    </span>
                    {stats.legacy_migrated ? (
                      <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-emerald-600 dark:text-emerald-400">
                        {t('stats.legacyMigrated')}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                        {t('stats.legacyPending')}
                      </span>
                    )}
                    {(stats.structural_issues?.broken_links ?? 0) > 0 && (
                      <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                        {t('stats.brokenLinks', { count: stats.structural_issues?.broken_links ?? 0 })}
                      </span>
                    )}
                    {(stats.structural_issues?.invalid_frontmatter_types ?? 0) > 0 && (
                      <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                        {t('stats.invalidPageTypes', {
                          count: stats.structural_issues?.invalid_frontmatter_types ?? 0,
                        })}
                      </span>
                    )}
                    {(stats.structural_issues?.provenance_gaps ?? 0) > 0 && (
                      <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                        {t('stats.provenanceGaps', {
                          count: stats.structural_issues?.provenance_gaps ?? 0,
                        })}
                      </span>
                    )}
                    {(stats.asset_index?.total_files ?? 0) > 0 && (
                      <span className="inline-flex items-center rounded-full bg-sky-500/10 px-3 py-1 text-sky-700 dark:text-sky-300">
                        {t('stats.indexedAssets', { count: stats.asset_index?.indexed ?? 0 })}
                      </span>
                    )}
                    {(stats.asset_index?.failed ?? 0) > 0 && (
                      <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                        {t('stats.failedAssets', { count: stats.asset_index?.failed ?? 0 })}
                      </span>
                    )}
                    {synthesisPendingCount > 0 && (
                      <button
                        type="button"
                        onClick={handleOpenSynthesisPending}
                        className="inline-flex items-center rounded-full bg-violet-500/10 px-3 py-1 text-violet-700 transition-colors hover:bg-violet-500/20 dark:text-violet-300"
                      >
                        {t('stats.synthesisPending', { count: synthesisPendingCount })}
                      </button>
                    )}
                    {duplicateGroupsPending > 0 && (
                      <button
                        type="button"
                        onClick={handleOpenDuplicateReview}
                        className={
                          dedupBlocksCompile
                            ? 'inline-flex items-center rounded-full bg-rose-500/10 px-3 py-1 text-rose-700 transition-colors hover:bg-rose-500/20 dark:text-rose-300'
                            : 'inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 transition-colors hover:bg-amber-500/20 dark:text-amber-300'
                        }
                      >
                        {t('stats.duplicateGroupsPending', { count: duplicateGroupsPending })}
                      </button>
                    )}
                    {stats.maintain_state?.last_run_at ? (
                      <span className="inline-flex items-center rounded-full bg-muted px-3 py-1 text-muted-foreground">
                        {stats.maintain_state.last_skipped_reason
                          ? maintainSkippedBadgeLabel(stats.maintain_state.last_skipped_reason, t)
                          : t('stats.lastMaintain', {
                              time: formatCognitiveUpdatedAt(stats.maintain_state.last_run_at, locale),
                            })}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-muted px-3 py-1 text-muted-foreground">
                        {t('stats.lastMaintainNever')}
                      </span>
                    )}
                  </div>
                  {stats.maintain_state?.last_run_at &&
                  !stats.maintain_state.last_skipped_reason &&
                  (stats.maintain_state.last_issues_found > 0 ||
                    stats.maintain_state.last_issues_fixed > 0) ? (
                    <p className="text-xs text-muted-foreground">
                      {t('stats.lastMaintainSummary', {
                        fixed: stats.maintain_state.last_issues_fixed,
                        found: stats.maintain_state.last_issues_found,
                      })}
                    </p>
                  ) : null}
                  {(stats.asset_index?.total_files ?? 0) > 0 && !stats.asset_index?.enabled ? (
                    <p className="text-xs text-amber-800/90 dark:text-amber-200/90">
                      {t('stats.assetsVisionHint')}
                    </p>
                  ) : null}
                  {(stats.structural_issues?.broken_links ?? 0) > 0 ||
                  (stats.structural_issues?.invalid_frontmatter_types ?? 0) > 0 ||
                  (stats.structural_issues?.provenance_gaps ?? 0) > 0 ? (
                    !healthReport && !isLoadingHealthReport && !healthReportLoadError ? (
                      <p className="text-xs text-amber-800/90 dark:text-amber-200/90">
                        {t('stats.structuralHint')}
                      </p>
                    ) : null
                  ) : null}
                  <WikiHealthIssuesSection
                    report={healthReport}
                    isLoading={
                      isLoadingHealthReport ||
                      (healthReport == null && !healthReportLoadError)
                    }
                    loadError={healthReportLoadError}
                    expanded={healthReportExpanded}
                    onToggleExpanded={() => setHealthReportExpanded((value) => !value)}
                    onRecompile={() => void handleCompile()}
                    isRecompiling={isCompiling}
                    onRepair={() => void handleRepairPageTypes()}
                    isRepairing={isRepairingTypes}
                    onNavigateIssue={navigateToHealthIssue}
                    onOpenDuplicateReview={handleOpenDuplicateReview}
                    onOpenPendingEdits={() => handleWikiTabChange('pendingEdits')}
                    onRefresh={() => void loadHealthReport()}
                  />
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                      <div className="text-xs text-muted-foreground">{t('stats.cognitiveIndex')}</div>
                      <div
                        className={
                          stats.cognitive_index_ready
                            ? 'mt-1 text-sm font-medium text-emerald-600 dark:text-emerald-400'
                            : 'mt-1 text-sm font-medium text-amber-700 dark:text-amber-400'
                        }
                      >
                        {stats.cognitive_index_ready ? t('stats.cognitiveReady') : t('stats.cognitivePending')}
                      </div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                      <div className="text-xs text-muted-foreground">{t('stats.cognitiveLog')}</div>
                      <div className="mt-1 text-sm font-medium text-foreground">
                        {t('stats.cognitiveLogEntries', { count: stats.cognitive_log_entries ?? 0 })}
                      </div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                      <div className="text-xs text-muted-foreground">{t('stats.cognitiveHot')}</div>
                      <div className="mt-1 text-sm font-medium text-foreground">
                        {stats.cognitive_hot_updated_at
                          ? t('stats.cognitiveHotUpdated', {
                              time: formatCognitiveUpdatedAt(stats.cognitive_hot_updated_at, locale),
                            })
                          : t('stats.cognitiveHotEmpty')}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-4 bg-muted rounded-lg">
                    <div className="text-3xl font-bold">{stats.total_concepts}</div>
                    <div className="text-sm text-muted-foreground">{t('stats.concepts')}</div>
                  </div>
                  <div className="text-center p-4 bg-muted rounded-lg">
                    <div className="text-3xl font-bold">{stats.total_articles}</div>
                    <div className="text-sm text-muted-foreground">{t('stats.articles')}</div>
                  </div>
                  <div className="text-center p-4 bg-muted rounded-lg">
                    <div className="text-3xl font-bold">{stats.total_raw_files}</div>
                    <div className="text-sm text-muted-foreground">{t('stats.rawFiles')}</div>
                  </div>
                  <div className="col-span-2 md:col-span-1 flex items-center justify-center">
                    <Button onClick={loadStats} variant="ghost" size="sm">
                      {t('actions.refresh')}
                    </Button>
                  </div>
                  </div>
                  <div className="space-y-2 border-t border-border/60 pt-4">
                    <div className="text-sm font-medium">{t('concepts.rawSourcesTitle')}</div>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-muted-foreground/40" />
                        {t('concepts.rawIngestNotCompiled')}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                        {t('concepts.rawIngestClean')}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-400" />
                        {t('concepts.rawIngestModified')}
                      </span>
                    </div>
                    <WikiRawSourceTree
                      treeData={rawTreeData}
                      isLoading={isLoadingRawTree}
                      agentScopeId={agentScopeId}
                      highlightPath={rawPathFromUrl}
                      onRawDeleted={() => void refreshIngestTreesSilently()}
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <ObsidianVaultActions
            agentScopeId={agentScopeId}
            wikiPath={stats?.wiki_path}
            vaultReady={stats?.vault_ready ?? false}
            obsidianLaunchAvailable={stats?.obsidian_launch_available ?? false}
            vaultGitEnabled={stats?.vault_git_enabled ?? false}
            vaultGitInitialized={stats?.vault_git_initialized ?? false}
            vaultGitLastCommit={stats?.vault_git_last_commit ?? null}
          />

          {/* Wiki Query */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconBook className="w-5 h-5" />
                {t('query.title')}
              </CardTitle>
              <CardDescription>{t('query.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
                <div className="flex w-full flex-col gap-1.5 lg:w-56">
                  <label htmlFor="wiki-query-mode" className="text-xs font-medium text-muted-foreground">
                    {t('query.modeLabel')}
                  </label>
                  <Select
                    value={queryMode}
                    onValueChange={(value) => setQueryMode(value as 'auto' | 'raw_claim')}
                  >
                    <SelectTrigger id="wiki-query-mode" className="w-full">
                      <SelectValue placeholder={t('query.modeAuto')}>
                        {queryMode === 'raw_claim' ? t('query.modeRawClaim') : t('query.modeAuto')}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">{t('query.modeAuto')}</SelectItem>
                      <SelectItem value="raw_claim">{t('query.modeRawClaim')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {queryMode === 'raw_claim' ? t('query.modeRawClaimHint') : t('query.modeAutoHint')}
                  </p>
                </div>
                <div className="flex w-full flex-1 flex-col gap-2 sm:flex-row">
                  <Input
                    placeholder={t('query.placeholder')}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                    className="flex-1"
                  />
                  <Button
                    onClick={handleQuery}
                    disabled={isQuerying || !query.trim()}
                    className="w-full sm:w-auto"
                  >
                    {isQuerying ? t('querying') : t('actions.query')}
                  </Button>
                </div>
              </div>

              {answer && (
                <div className="space-y-2">
                  {queryConfidence !== null && (
                    <div className="text-xs text-muted-foreground">
                      {t('query.confidenceScore', {
                        value: formatClaimConfidence(queryConfidence, locale),
                      })}
                    </div>
                  )}
                  <div className="text-sm font-medium">{t('query.answer')}</div>
                  <div className="p-4 bg-muted rounded-lg whitespace-pre-wrap">{answer}</div>

                  {retrievalTrace &&
                    (retrievalTrace.index_hits.length > 0 ||
                      retrievalTrace.seeds.length > 0 ||
                      retrievalTrace.sidecar_directories.length > 0 ||
                      retrievalTrace.selected_concepts.length > 0) && (
                      <div className="mt-4 space-y-2 rounded-lg border border-border/60 bg-card/40 p-3">
                        <div className="text-sm font-medium">{t('query.retrievalTraceTitle')}</div>
                        {retrievalTrace.index_hits.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceIndex')}</div>
                            {retrievalTrace.index_hits.map((hit) => (
                              <div key={hit.link_name} className="text-xs text-muted-foreground">
                                [[{hit.link_name}]] — {hit.summary}
                              </div>
                            ))}
                          </div>
                        )}
                        {retrievalTrace.sidecar_directories.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceSidecar')}</div>
                            <div className="text-xs text-muted-foreground font-mono break-all">
                              {retrievalTrace.sidecar_directories.join(' · ')}
                            </div>
                          </div>
                        )}
                        {retrievalTrace.seeds.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceSeeds')}</div>
                            <div className="space-y-1">
                              {retrievalTrace.seeds.slice(0, 6).map((seed) => (
                                <div key={`${seed.source}-${seed.concept_name}`} className="text-xs text-muted-foreground font-mono break-all">
                                  {seed.concept_name} ({seed.source})
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {retrievalTrace.selected_concepts.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceConcepts')}</div>
                            <div className="text-xs text-muted-foreground font-mono">
                              {retrievalTrace.selected_concepts.join(' · ')}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                  {sourceSnippets.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <div className="text-sm font-medium">{tSources('sources_title')}</div>
                      <div className="space-y-2">
                        {sourceSnippets.map((snippet, idx) => {
                          const level = normalizeWikiLevel(snippet.level);
                          const isAssetHit = snippet.hit_kind === 'asset' && snippet.asset_filename;
                          const levelLabel = level
                            ? level === 'L0'
                              ? tSources('kb_level_l0')
                              : level === 'L1'
                                ? tSources('kb_level_l1')
                                : tSources('kb_level_l2')
                            : null;
                          const cardTitle = snippet.name || snippet.path;
                          const sectionLabel = resolveWikiSectionLabel(snippet.section || undefined, tSources);
                          const thumbnailUrl = isAssetHit
                            ? buildWikiAssetUrl(snippet.asset_filename!, agentScopeId)
                            : null;
                          return (
                            <button
                              key={`${snippet.path}-${idx}`}
                              type="button"
                              className="w-full text-left rounded-lg border border-border/60 bg-card px-3 py-2 hover:bg-muted transition-colors"
                              onClick={() =>
                                setSnippetDrawerState({
                                  open: true,
                                  title: cardTitle,
                                  section: sectionLabel,
                                  snippet: snippet.snippet,
                                  level,
                                  snapshotStatus: snippet.snapshot_status,
                                  claimStatus: snippet.claim_status,
                                  claimConfidence: snippet.claim_confidence,
                                  claimText: snippet.claim_text,
                                  resourceUri: snippet.resource_uri,
                                  supersededFromUri: snippet.superseded_from_uri,
                                  thumbnailUrl,
                                })
                              }
                            >
                              <div className="flex items-start gap-3">
                                {thumbnailUrl ? (
                                  <img
                                    src={thumbnailUrl}
                                    alt=""
                                    className="h-14 w-14 shrink-0 rounded-md border border-border/60 object-cover bg-muted"
                                  />
                                ) : null}
                                <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-sm font-medium truncate">{cardTitle}</span>
                                {levelLabel && (
                                  <span className="text-[10px] leading-4 px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                                    {levelLabel}
                                  </span>
                                )}
                              </div>
                              {sectionLabel && <div className="mt-1 text-xs text-muted-foreground">{sectionLabel}</div>}
                              {snippet.path && (
                                <div className="mt-1 text-[11px] text-muted-foreground truncate font-mono">{snippet.path}</div>
                              )}
                              {snippet.snippet && (
                                <p className="mt-2 text-xs text-muted-foreground line-clamp-3">{snippet.snippet}</p>
                              )}
                              {snippet.claim_id && (
                                <p className="mt-1 text-[11px] text-primary/80 font-mono truncate">
                                  {snippet.evidence_path}
                                  {snippet.line_range ? ` · L${snippet.line_range}` : ''}
                                </p>
                              )}
                              {snippet.snapshot_status === 'verified' && (
                                <p className="mt-1 text-[11px] text-emerald-700 dark:text-emerald-300">
                                  {t('evidenceSnapshotVerified')}
                                </p>
                              )}
                              {snippet.snapshot_status === 'stale' && (
                                <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
                                  {t('evidenceSnapshotStale')}
                                </p>
                              )}
                              {snippet.snapshot_status === 'missing' && snippet.evidence_path && (
                                <p className="mt-1 text-[11px] text-muted-foreground">
                                  {t('evidenceSnapshotMissing')}
                                </p>
                              )}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {relatedArticles.length > 0 && (
                    <div className="mt-4">
                      <div className="text-sm font-medium mb-2">{t('query.relatedArticles')}</div>
                      <div className="flex flex-wrap gap-2">
                        {relatedArticles.map((article, idx) => (
                          <span key={idx} className="px-2 py-1 bg-primary/10 text-primary rounded text-sm">
                            {article}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
          <SourceChunkDrawer
            open={snippetDrawerState.open}
            onOpenChange={(open) => setSnippetDrawerState((prev) => ({ ...prev, open }))}
            title={snippetDrawerState.title}
            section={snippetDrawerState.section}
            snippet={snippetDrawerState.snippet}
            level={snippetDrawerState.level}
            snapshotStatus={snippetDrawerState.snapshotStatus}
            claimStatus={snippetDrawerState.claimStatus}
            claimConfidence={snippetDrawerState.claimConfidence}
            claimText={snippetDrawerState.claimText}
            resourceUri={snippetDrawerState.resourceUri}
            supersededFromUri={snippetDrawerState.supersededFromUri}
            thumbnailUrl={snippetDrawerState.thumbnailUrl}
            surface="settings"
            contextKey={evidenceContextKey}
          />

          {/* Wiki Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconWrench className="w-5 h-5" />
                {t('actions.title')}
              </CardTitle>
              <CardDescription>{t('actions.description')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {compileRun?.state === 'paused' && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 space-y-3">
                  <div className="text-sm font-medium text-amber-800 dark:text-amber-200">
                    {t('compileRun.pausedTitle')}
                  </div>
                  <p className="text-sm text-amber-900/80 dark:text-amber-100/80">
                    {compileRun.pause_reason || t('compileRun.pausedDefault')}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={isResumingCompile} onClick={() => void handleResumeCompile()}>
                      {isResumingCompile ? t('compileRun.resuming') : t('compileRun.resume')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => handleWikiTabChange('queue')}>
                      {t('compileRun.viewQueue')}
                    </Button>
                  </div>
                </div>
              )}
              {compileRun && compileRun.state !== 'paused' && (
                <WikiCompilePhaseBar
                  compileRun={compileRun}
                  pendingCount={ingestSnapshot?.stats.pending ?? 0}
                  processingCount={ingestSnapshot?.stats.processing ?? 0}
                  forceVisible={isCompiling}
                />
              )}
              <div className="space-y-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <label htmlFor="wiki-maintain-mode" className="text-sm font-medium text-foreground">
                    {t('actions.maintainModeLabel')}
                  </label>
                  <Select
                    value={maintainMode}
                    onValueChange={(value) => setMaintainMode(value as 'structural' | 'full')}
                  >
                    <SelectTrigger id="wiki-maintain-mode" className="w-full sm:w-64">
                      <SelectValue placeholder={t('actions.maintainModeStructural')}>
                        {maintainMode === 'full'
                          ? t('actions.maintainModeFull')
                          : t('actions.maintainModeStructural')}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="structural">{t('actions.maintainModeStructural')}</SelectItem>
                      <SelectItem value="full">{t('actions.maintainModeFull')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-xs text-muted-foreground">
                  {isWikiCompileBusy
                    ? t('actions.maintainCompileBusyHint')
                    : maintainMode === 'full'
                      ? t('actions.maintainModeFullHint')
                      : t('actions.maintainModeStructuralHint')}
                </p>
              </div>
              <div className="flex flex-col sm:flex-row sm:flex-wrap gap-4">
              <Button
                onClick={handleCompile}
                disabled={isCompiling || compileRun?.state === 'paused'}
                className="flex-1"
              >
                <IconGlow className="w-4 h-4 mr-2" />
                {isCompiling ? t('compiling') : t('actions.compile')}
              </Button>
              <Button
                onClick={handleMaintain}
                disabled={isMaintaining || isWikiCompileBusy}
                variant="outline"
                className="flex-1"
              >
                <IconWrench className="w-4 h-4 mr-2" />
                {isMaintaining ? t('maintaining') : t('actions.maintain')}
              </Button>
              <Button
                onClick={handleRepairPageTypes}
                disabled={isRepairingTypes}
                variant="outline"
                className="flex-1"
              >
                <IconWrench className="w-4 h-4 mr-2" />
                {isRepairingTypes ? t('repairingTypes') : t('actions.repairPageTypes')}
              </Button>
              <Button
                onClick={handleRepairPublication}
                disabled={isRepairingPublication}
                variant="outline"
                className="flex-1"
              >
                <IconWrench className="w-4 h-4 mr-2" />
                {isRepairingPublication ? t('repairingPublication') : t('actions.repairPublication')}
              </Button>
              <Button
                onClick={() => void handleReindexVectors()}
                disabled={isReindexingVectors || isWikiCompileBusy}
                variant="outline"
                className="flex-1"
              >
                <IconDatabase className="w-4 h-4 mr-2" />
                {isReindexingVectors ? t('reindexingVectors') : t('actions.reindexVectors')}
              </Button>
              </div>
              {reindexErrors.length > 0 ? (
                <div
                  className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm"
                  data-testid="wiki-reindex-errors"
                >
                  <p className="font-medium text-amber-800 dark:text-amber-200">
                    {t('reindexErrorsTitle', { count: reindexErrors.length })}
                  </p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
                    {reindexErrors.slice(0, 8).map((entry, index) => (
                      <li key={`${index}-${entry}`} className="break-all">
                        {entry}
                      </li>
                    ))}
                  </ul>
                  {reindexErrors.length > 8 ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {t('reindexErrorsTruncated', { count: reindexErrors.length - 8 })}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {/* Batch Import */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconDatabase className="w-5 h-5" />
                {t('import.title')}
              </CardTitle>
              <CardDescription>{t('import.description')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col sm:flex-row gap-4">
              <Button onClick={handleImportFolder} disabled={isImporting} variant="outline" className="flex-1">
                <IconExplore className="w-4 h-4 mr-2" />
                {isImporting ? t('import.importing') : t('import.folder')}
              </Button>
              <Button
                onClick={() => zipInputRef.current?.click()}
                disabled={isImporting}
                variant="outline"
                className="flex-1"
              >
                <IconBook className="w-4 h-4 mr-2" />
                {isImporting ? t('import.importing') : t('import.zip')}
              </Button>
              <input
                ref={zipInputRef}
                type="file"
                accept=".zip"
                onChange={handleImportZip}
                className="hidden"
              />
              {!isTauriEnv && (
                <input
                  ref={webFolderInputRef}
                  type="file"
                  // @ts-expect-error -- webkitdirectory is non-standard but supported by all major browsers
                  webkitdirectory=""
                  onChange={handleWebFolderSelect}
                  className="hidden"
                />
              )}
            </CardContent>
          </Card>

          <WikiIgnorePanel />

          {/* Obsidian Vault Import */}
          <Card id="wiki-obsidian-import">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconBook className="w-5 h-5" />
                {t('import.obsidianTitle')}
              </CardTitle>
              <CardDescription>{t('import.obsidianDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col sm:flex-row gap-4">
              {isTauriEnv && (
                <Button
                  onClick={handleImportObsidianFolder}
                  disabled={isImportingObsidian}
                  variant="outline"
                  className="flex-1"
                >
                  <IconExplore className="w-4 h-4 mr-2" />
                  {isImportingObsidian ? t('import.importing') : t('import.obsidianFolder')}
                </Button>
              )}
              <Button
                onClick={() => obsidianZipRef.current?.click()}
                disabled={isImportingObsidian}
                variant="outline"
                className="flex-1"
              >
                <IconDatabase className="w-4 h-4 mr-2" />
                {isImportingObsidian ? t('import.importing') : t('import.obsidianZip')}
              </Button>
              <input
                ref={obsidianZipRef}
                type="file"
                accept=".zip"
                onChange={handleImportObsidianZip}
                className="hidden"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="concepts" className="space-y-6 flex flex-col flex-1 min-h-0">
          <WikiConceptsList
            key={`${agentScopeId ?? 'default'}-${scopeRevision}`}
            treeSyncNonce={treeSyncNonce}
            agentScopeId={agentScopeId}
            highlightConceptPath={conceptPathFromUrl}
            onVaultMutated={() => {
              void loadStats();
            }}
          />
        </TabsContent>

        <TabsContent value="pendingEdits" className="space-y-6">
          <WikiPendingEdits
            agentScopeId={agentScopeId}
            scopeLabel={scopeLabel}
            initialFilter={pendingEditsInitialFilter}
            onVaultMutated={() => {
              void loadStats();
            }}
          />
        </TabsContent>

        <TabsContent value="duplicateReview" className="space-y-6">
          <WikiDuplicateReviewPanel
            agentScopeId={agentScopeId}
            scopeLabel={scopeLabel}
            onVaultMutated={() => {
              void loadStats();
            }}
          />
        </TabsContent>

        <TabsContent value="queue" className="space-y-6">
          <WikiQueuePanel
            agentScopeId={agentScopeId}
            scopeLabel={scopeLabel}
            liveIngestConnected={ingestLive}
            liveIngestSnapshot={ingestSnapshot}
          />
        </TabsContent>
      </Tabs>
      <WikiImportConflictDialog
        open={importConflictOpen}
        conflictPaths={importConflictPaths}
        onClose={() => {
          setImportConflictOpen(false);
          setPendingImportRetry(null);
          setImportConflictPaths([]);
        }}
        onKeepSkipped={() => {
          toast.message(t('import.conflictSkippedToast', { count: importConflictPaths.length }));
          setImportConflictOpen(false);
          setPendingImportRetry(null);
          setImportConflictPaths([]);
        }}
        onSupersede={retryImportWithSupersede}
      />
      <WikiImportSecurityDialog
        open={importSecurityOpen}
        blockedPaths={importSecurityBlockedPaths}
        redactedPaths={importSecurityRedactedPaths}
        onClose={() => {
          setImportSecurityOpen(false);
          setImportSecurityBlockedPaths([]);
          setImportSecurityRedactedPaths([]);
        }}
      />
      </div>
    </WikiAgentScopeProvider>
  );
}

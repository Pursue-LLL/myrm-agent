import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  LazyMonacoEditor as Editor,
  LazyMonacoDiffEditor as DiffEditor,
} from '@/components/features/app-shell/lazy-monaco-editor';
import { toast } from 'sonner';
import {
  RefreshCw,
  Play,
  Save,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Eye,
  Plus,
  Grid3X3,
  Loader2,
  Clock,
  BrainCircuit,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from '@/components/features/app-shell/lazy-recharts';
import MatrixResultView, { type MatrixReportData } from './MatrixResultView';
import CaseFormatReference from './CaseFormatReference';
import WbBenchSources from './WbBenchSources';
import MemoryAbHistoryTable, { type MemoryAbHistoryItem } from './MemoryAbHistoryTable';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

interface EvalDataset {
  id: string;
  filename?: string;
  updated_at?: number;
  size?: number;
}

interface EvalProfile {
  agent_id: string;
  name: string;
}

interface ReportItem {
  timestamp?: number;
  total?: number;
  passed?: number;
  filename?: string;
  manifest?: {
    task_set_id?: string;
    profile_id?: string;
    model_provider?: string;
    model_id?: string;
    benchmark_mode?: boolean;
    thinking_effort?: string;
    harness_version?: string;
    tool_policy?: string[];
    prompt_fingerprint?: string;
  };
  avg_time_secs?: number;
  avg_total_tokens?: number;
  cases?: Array<{
    passed: boolean | null;
    time_secs?: number;
    details?: unknown;
    scores?: { pass_rate?: number; tests_passed?: number; tests_total?: number };
    usage?: { total_tokens?: number };
    actual_tools?: unknown[];
    actual_output?: string;
    case?: {
      message?: string;
      expected_tools?: unknown[];
      state_assertions?: unknown[];
    };
  }>;
}

function formatMib(bytes: number): string {
  if (bytes <= 0) return '0 MB';
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function EvalLabDashboard() {
  const locale = useLocale();
  const t = useTranslations('evalLab');
  const [cases, setCases] = useState('');
  const [casesDraft, setCasesDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ total: 0, completed: 0 });
  const [evalStage, setEvalStage] = useState<string | null>(null);
  const [evalStageSubsetId, setEvalStageSubsetId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{
    downloaded_bytes: number;
    total_bytes: number;
  } | null>(null);
  const [sourcesRefreshToken, setSourcesRefreshToken] = useState(0);
  const [report, setReport] = useState<ReportItem | null>(null);
  const [history, setHistory] = useState<ReportItem[]>([]);
  const [activeTab, setActiveTab] = useState('cases');
  const [diffView, setDiffView] = useState<{ expected: string; actual: string } | null>(null);
  const [profiles, setProfiles] = useState<EvalProfile[]>([]);
  const [selectedProfileIds, setSelectedProfileIds] = useState<string[]>([]);
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('default');
  const [benchmarkMode, setBenchmarkMode] = useState(false);
  const [loadingReport, setLoadingReport] = useState<string | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('new_dataset');
  const createInputRef = useRef<HTMLInputElement>(null);
  const [matrixReport, setMatrixReport] = useState<MatrixReportData | null>(null);
  const [matrixRunning, setMatrixRunning] = useState(false);
  const [matrixProgress, setMatrixProgress] = useState({
    current_profile: '',
    profile_progress: 0,
    profile_total: 0,
    case_completed: 0,
    case_total: 0,
  });
  const [memoryAbReport, setMemoryAbReport] = useState<MatrixReportData | null>(null);
  const [memoryAbRunning, setMemoryAbRunning] = useState(false);
  const [memoryAbProgress, setMemoryAbProgress] = useState({
    current_arm: '',
    stage: '',
    profile_progress: 0,
    profile_total: 0,
    case_completed: 0,
    case_total: 0,
    download_progress: null as { downloaded_bytes: number; total_bytes: number } | null,
  });
  const [memoryAbHistory, setMemoryAbHistory] = useState<MemoryAbHistoryItem[]>([]);
  const [selectedMemoryAbTs, setSelectedMemoryAbTs] = useState<number | null>(null);

  const isMatrixMode = selectedProfileIds.length >= 2;

  const memoryAbProfileNames = useCallback(
    () => ({
      memory_off: t('memoryAb.armNoMemory'),
      memory_on: t('memoryAb.armWithMemory'),
    }),
    [t],
  );

  const fetchDatasets = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/datasets');
      const data = (await res.json()) as { status?: string; datasets?: EvalDataset[] };
      if (data.status === 'success' && data.datasets) {
        setDatasets(data.datasets);
      }
    } catch (e) {
      console.error('Failed to fetch datasets:', e);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/reports');
      const data = await res.json();
      if (data.status === 'success' && data.reports) {
        setHistory(data.reports.reverse());
      }
    } catch (e) {
      console.error('Failed to fetch reports history:', e);
    }
  }, []);

  const fetchProfiles = useCallback(async () => {
    try {
      const { listAgents } = await import('@/services/agent');
      const res = await listAgents(1, 200);
      setProfiles(
        res.items.map((item) => ({ agent_id: item.id, name: getBuiltinAgentName(item.id, item.name, locale) })),
      );
    } catch (e) {
      console.error('Failed to fetch profiles', e);
    }
  }, [locale]);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/status');
      const data = await res.json();
      setRunning(data.is_running);
      setProgress({ total: data.total ?? 0, completed: data.completed ?? 0 });
      setEvalStage(data.stage ?? null);
      setEvalStageSubsetId(data.stage_subset_id ?? null);
      if (data.download_progress) {
        setDownloadProgress(data.download_progress);
      }

      if (!data.is_running && running) {
        fetchReport();
      }
    } catch (e) {
      console.error(e);
    }
  }, [running]);

  const fetchCases = useCallback(
    async (datasetId: string) => {
      try {
        const res = await fetch(`/api/v1/eval/datasets/${datasetId}`);
        const data = await res.json();
        if (data.status === 'success') {
          setCases(data.content);
          setCasesDraft(data.content);
        }
      } catch {
        toast.error(t('fetchCasesFailed'));
      }
    },
    [t],
  );

  const fetchReport = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/reports/latest');
      const data = (await res.json()) as { status?: string; summary?: ReportItem };
      if (data.status === 'success' && data.summary) {
        setReport(data.summary);
      }
    } catch (e) {
      console.error('Failed to fetch latest report:', e);
    }
  }, []);

  const fetchMatrixReport = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/matrix/reports/latest');
      const data = await res.json();
      if (data.status === 'success' && data.report) {
        setMatrixReport(data.report as MatrixReportData);
      }
    } catch (e) {
      console.error('Failed to fetch matrix report:', e);
    }
  }, []);

  const fetchMemoryAbReport = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/memory-ab/reports/latest');
      const data = await res.json();
      if (data.status === 'success' && data.report) {
        const report = data.report as MatrixReportData & { timestamp?: number };
        setMemoryAbReport(report);
        setSelectedMemoryAbTs(report.timestamp ?? null);
      }
    } catch (e) {
      console.error('Failed to fetch memory A/B report:', e);
    }
  }, []);

  const fetchMemoryAbHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/memory-ab/reports/history');
      const data = (await res.json()) as { status?: string; reports?: MemoryAbHistoryItem[] };
      if (data.status === 'success' && Array.isArray(data.reports)) {
        setMemoryAbHistory(data.reports);
      }
    } catch (e) {
      console.error('Failed to fetch memory A/B history:', e);
    }
  }, []);

  const loadMemoryAbReport = useCallback(
    async (timestamp: number) => {
      try {
        const res = await fetch(`/api/v1/eval/memory-ab/reports/${timestamp}`);
        const data = (await res.json()) as { status?: string; report?: MatrixReportData | null };
        if (data.status === 'success' && data.report) {
          setMemoryAbReport(data.report);
          setSelectedMemoryAbTs(timestamp);
        } else {
          toast.error(t('loadReportFailed'));
        }
      } catch (e) {
        console.error('Failed to load memory A/B report:', e);
        toast.error(t('loadReportFailed'));
      }
    },
    [t],
  );

  useEffect(() => {
    Promise.all([
      fetchDatasets(),
      fetchStatus(),
      fetchReport(),
      fetchProfiles(),
      fetchHistory(),
      fetchMatrixReport(),
      fetchMemoryAbReport(),
      fetchMemoryAbHistory(),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedDatasetId) {
      fetchCases(selectedDatasetId);
    }
  }, [selectedDatasetId, fetchCases]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    if (running) {
      eventSource = new EventSource('/api/v1/eval/stream');

      let finalized = false;
      const finalize = () => {
        if (finalized) return;
        finalized = true;
        eventSource?.close();
        setRunning(false);
        setSourcesRefreshToken((prev) => prev + 1);
        fetchReport();
        fetchHistory();
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setRunning(data.is_running);
          setProgress({ total: data.total ?? 0, completed: data.completed ?? 0 });
          setEvalStage(data.stage ?? null);
          setEvalStageSubsetId(data.stage_subset_id ?? null);
          if (data.download_progress) {
            setDownloadProgress(data.download_progress);
          }

          if (!data.is_running) {
            if (data.error) {
              toast.error(data.error);
            }
            finalize();
          }
        } catch (e) {
          console.error('Failed to parse SSE data', e);
        }
      };

      eventSource.addEventListener('close', finalize);

      eventSource.onerror = () => {
        console.error('SSE Error');
        eventSource?.close();
        // A fast task (e.g. a cached-archive download) can finish before the
        // EventSource connects, making the stream EOF immediately and firing
        // onerror instead of onmessage. Always re-pull sources so the UI is not
        // left showing stale downloadable buttons after a completed run.
        setRunning(false);
        setSourcesRefreshToken((prev) => prev + 1);
        fetchReport();
        fetchHistory();
      };
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [running, fetchReport]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    if (matrixRunning) {
      eventSource = new EventSource('/api/v1/eval/matrix/stream');

      let finalized = false;
      const finalize = () => {
        if (finalized) return;
        finalized = true;
        eventSource?.close();
        setMatrixRunning(false);
        fetchMatrixReport();
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMatrixRunning(!!data.is_running);
          setMatrixProgress({
            current_profile: data.current_profile || '',
            profile_progress: data.profile_progress || 0,
            profile_total: data.profile_total || 0,
            case_completed: data.case_completed || 0,
            case_total: data.case_total || 0,
          });
          if (!data.is_running) {
            if (data.error) {
              toast.error(data.error);
            }
            finalize();
          }
        } catch (e) {
          console.error('Matrix SSE parse error', e);
        }
      };
      eventSource.addEventListener('close', finalize);
      eventSource.onerror = () => {
        eventSource?.close();
        setMatrixRunning(false);
      };
    }
    return () => {
      eventSource?.close();
    };
  }, [matrixRunning]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    if (memoryAbRunning) {
      eventSource = new EventSource('/api/v1/eval/memory-ab/stream');

      let finalized = false;
      const finalize = () => {
        if (finalized) return;
        finalized = true;
        eventSource?.close();
        setMemoryAbRunning(false);
        setSourcesRefreshToken((prev) => prev + 1);
        fetchMemoryAbReport();
        fetchMemoryAbHistory();
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMemoryAbRunning(!!data.is_running);
          setMemoryAbProgress({
            current_arm: data.current_arm || '',
            stage: data.stage || '',
            profile_progress: data.profile_progress || 0,
            profile_total: data.profile_total || 0,
            case_completed: data.case_completed || 0,
            case_total: data.case_total || 0,
            download_progress: data.download_progress || null,
          });
          if (!data.is_running) {
            if (data.error) {
              toast.error(data.error);
            }
            finalize();
          }
        } catch (e) {
          console.error('Memory A/B SSE parse error', e);
        }
      };
      eventSource.addEventListener('close', finalize);
      eventSource.onerror = () => {
        eventSource?.close();
        setMemoryAbRunning(false);
        // A fast run can finish before the EventSource connects, making the
        // stream EOF immediately and firing onerror instead of onmessage.
        // Re-pull the report and history so the UI never shows stale state.
        fetchMemoryAbReport();
        fetchMemoryAbHistory();
      };
    }
    return () => {
      eventSource?.close();
    };
  }, [memoryAbRunning, fetchMemoryAbReport, fetchMemoryAbHistory]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/eval/datasets/${selectedDatasetId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: casesDraft }),
      });
      if (res.ok) {
        toast.success(t('saveCasesSuccess'));
        setCases(casesDraft);
      } else {
        toast.error(t('saveFailed'));
      }
    } catch {
      toast.error(t('saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (running || matrixRunning || memoryAbRunning) return;
    if (cases !== casesDraft) {
      toast.error(t('saveFirst'));
      return;
    }

    if (isMatrixMode) {
      try {
        const res = await fetch('/api/v1/eval/matrix/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            profile_ids: selectedProfileIds,
            dataset_id: selectedDatasetId,
            benchmark_mode: benchmarkMode,
          }),
        });
        const data = await res.json();
        if (data.status === 'started' || data.status === 'already_running') {
          setMatrixRunning(true);
          toast.success(t('matrixEvalStarted'));
          setActiveTab('matrix');
        }
      } catch {
        toast.error(t('evalStartFailed'));
      }
    } else {
      try {
        const res = await fetch('/api/v1/eval/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            profile_id: selectedProfileIds[0] || null,
            dataset_id: selectedDatasetId,
            benchmark_mode: benchmarkMode,
          }),
        });
        const data = await res.json();
        if (data.status === 'started' || data.status === 'already_running') {
          setRunning(true);
          toast.success(t('evalStarted'));
          setActiveTab('report');
        }
      } catch {
        toast.error(t('evalStartFailed'));
      }
    }
  };

  const handleWbRun = async (subsetId: string) => {
    if (running || matrixRunning || memoryAbRunning) return;
    try {
      const res = await fetch('/api/v1/eval/wb-bench/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subset_id: subsetId,
          profile_id: selectedProfileIds[0] || null,
          benchmark_mode: benchmarkMode,
        }),
      });
      const data = await res.json();
      if (data.status === 'started') {
        setRunning(true);
        toast.success(t('wbBenchRunStarted'));
        setActiveTab('report');
      } else if (data.status === 'already_running') {
        toast.info(t('alreadyRunning'));
      } else {
        toast.error(data.error || t('evalStartFailed'));
      }
    } catch {
      toast.error(t('evalStartFailed'));
    }
  };

  const handleWbDownload = async (subsetId: string) => {
    if (running || matrixRunning || memoryAbRunning) return;
    try {
      const res = await fetch('/api/v1/eval/wb-bench/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subset_id: subsetId }),
      });
      const data = await res.json();
      if (data.status === 'started') {
        setRunning(true);
        setActiveTab('sources');
      } else if (data.status === 'already_running') {
        toast.info(t('alreadyRunning'));
      } else {
        toast.error(data.error || t('evalStartFailed'));
      }
    } catch {
      toast.error(t('evalStartFailed'));
    }
  };

  const handleMemoryAbRun = async (subsetId: string) => {
    if (running || matrixRunning || memoryAbRunning) return;
    try {
      const res = await fetch('/api/v1/eval/memory-ab/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subset_id: subsetId,
          profile_id: selectedProfileIds[0] || null,
        }),
      });
      const data = await res.json();
      if (data.status === 'started') {
        setMemoryAbRunning(true);
        toast.success(t('memoryAb.started'));
        setActiveTab('memory-ab');
      } else if (data.status === 'already_running') {
        toast.info(t('alreadyRunning'));
      } else {
        toast.error(data.error || t('evalStartFailed'));
      }
    } catch {
      toast.error(t('evalStartFailed'));
    }
  };

  const handleAbort = async () => {
    try {
      const endpoint = memoryAbRunning
        ? '/api/v1/eval/memory-ab/abort'
        : matrixRunning
          ? '/api/v1/eval/matrix/abort'
          : '/api/v1/eval/abort';
      const res = await fetch(endpoint, { method: 'POST' });
      if (res.ok) {
        toast.success(t('abortSent'));
      }
    } catch {
      toast.error(t('abortFailed'));
    }
  };

  const handleCreateDataset = async () => {
    const name = newDatasetName.trim();
    if (!name) return;
    setCreateDialogOpen(false);
    try {
      const res = await fetch(`/api/v1/eval/datasets/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: '' }),
      });
      if (res.ok) {
        toast.success(t('datasetCreated'));
        await fetchDatasets();
        setSelectedDatasetId(name);
        setNewDatasetName('new_dataset');
      } else {
        toast.error(t('createFailed'));
      }
    } catch {
      toast.error(t('createFailed'));
    }
  };

  const viewDiff = (expected: string, actual: string) => {
    setDiffView({ expected, actual });
    setActiveTab('diff');
  };

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">{t('loading')}</div>;
  }

  const successRate =
    report && typeof report.total === 'number' && report.total > 0
      ? Math.round(((report.passed ?? 0) / report.total) * 100)
      : 0;

  return (
    <div className="flex flex-col h-full bg-card rounded-xl border overflow-hidden">
      <div className="flex items-center justify-between p-4 border-b bg-muted/20">
        <div className="flex items-center gap-4">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-auto">
            <TabsList>
              <TabsTrigger value="cases">{t('tabs.cases')}</TabsTrigger>
              <TabsTrigger value="sources">{t('tabs.sources')}</TabsTrigger>
              <TabsTrigger value="report">{t('tabs.report')}</TabsTrigger>
              {(matrixReport || matrixRunning) && <TabsTrigger value="matrix">{t('tabs.matrix')}</TabsTrigger>}
              {(memoryAbReport || memoryAbRunning) && <TabsTrigger value="memory-ab">{t('tabs.memoryAb')}</TabsTrigger>}
              <TabsTrigger value="history">{t('tabs.history')}</TabsTrigger>
              {diffView && <TabsTrigger value="diff">{t('tabs.diff')}</TabsTrigger>}
            </TabsList>
          </Tabs>
        </div>

        <div className="flex items-center gap-3">
          {running && (
            <div className="flex items-center gap-2 text-sm">
              <RefreshCw className="w-4 h-4 animate-spin text-primary" />
              <span>
                {evalStage === 'downloading'
                  ? `${t('wbBench.downloading')}: ${formatMib(downloadProgress?.downloaded_bytes ?? 0)} / ${
                      downloadProgress && downloadProgress.total_bytes > 0
                        ? formatMib(downloadProgress.total_bytes)
                        : '?'
                    }`
                  : `${t('progress')}: ${progress.completed} / ${progress.total}`}
              </span>
            </div>
          )}

          {activeTab === 'cases' && cases !== casesDraft && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-full hover:bg-primary/90 disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {t('save')}
            </button>
          )}

          <div className="flex items-center border rounded-full bg-background px-1">
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className="px-2 py-1.5 text-sm bg-transparent outline-none cursor-pointer"
              disabled={running}
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.id === 'default' ? `${t('defaultDataset')} (default)` : d.id}
                </option>
              ))}
              {datasets.length === 0 && <option value="default">{t('defaultDataset')} (default)</option>}
            </select>
            <button
              onClick={() => setCreateDialogOpen(true)}
              disabled={running}
              className="p-1 hover:bg-muted rounded text-muted-foreground transition-colors"
              title={t('createDataset')}
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-center gap-1 flex-wrap max-w-[400px]">
            {profiles.map((p) => {
              const isSelected = selectedProfileIds.includes(p.agent_id);
              return (
                <button
                  key={p.agent_id}
                  onClick={() => {
                    if (running || matrixRunning || memoryAbRunning) return;
                    setSelectedProfileIds((prev) =>
                      isSelected ? prev.filter((id) => id !== p.agent_id) : [...prev, p.agent_id],
                    );
                  }}
                  disabled={running || matrixRunning || memoryAbRunning}
                  className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                    isSelected
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-background text-muted-foreground border-border hover:border-primary/50'
                  } disabled:opacity-50`}
                >
                  {p.name || p.agent_id.slice(0, 8)}
                </button>
              );
            })}
            {isMatrixMode && (
              <span className="flex items-center gap-1 text-xs text-primary font-medium ml-1">
                <Grid3X3 className="w-3 h-3" />
                {t('matrixMode')}
              </span>
            )}
          </div>

          <label className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={benchmarkMode}
              onChange={(e) => setBenchmarkMode(e.target.checked)}
              disabled={running || matrixRunning || memoryAbRunning}
              className="rounded border-border text-primary focus:ring-primary"
            />
            {t('benchmarkMode')}
          </label>

          <button
            onClick={handleRun}
            disabled={running || matrixRunning || memoryAbRunning}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-green-600 text-white rounded-full hover:bg-green-700 disabled:opacity-50 disabled:bg-gray-400"
          >
            <Play className="w-4 h-4" />
            {running || matrixRunning || memoryAbRunning ? t('running') : isMatrixMode ? t('runMatrix') : t('run')}
          </button>

          {(running || matrixRunning || memoryAbRunning) && (
            <button
              onClick={handleAbort}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-red-600 text-white rounded-full hover:bg-red-700"
            >
              <XCircle className="w-4 h-4" />
              {t('stop')}
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative">
        <Tabs value={activeTab} className="h-full">
          <TabsContent value="cases" className="h-full p-0 m-0 flex flex-col">
            <CaseFormatReference t={t} />
            <div className="flex-1 min-h-0">
              <Editor
                height="100%"
                defaultLanguage="json"
                theme="vs-dark"
                value={casesDraft}
                onChange={(value) => setCasesDraft(value || '')}
                options={{ minimap: { enabled: false }, wordWrap: 'on' }}
              />
            </div>
          </TabsContent>

          <TabsContent value="sources" className="h-full p-6 m-0">
            <WbBenchSources
              running={running || matrixRunning || memoryAbRunning}
              history={history}
              onRun={handleWbRun}
              onDownload={handleWbDownload}
              onMemoryAb={handleMemoryAbRun}
              refreshToken={sourcesRefreshToken}
              downloadingSubsetId={evalStage === 'downloading' ? evalStageSubsetId : null}
              downloadProgress={downloadProgress}
            />
          </TabsContent>

          <TabsContent value="report" className="h-full p-6 overflow-y-auto">
            {running ? (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <RefreshCw className="w-8 h-8 animate-spin text-primary" />
                <p>
                  {evalStage === 'downloading'
                    ? `${t('wbBench.downloading')}: ${formatMib(downloadProgress?.downloaded_bytes ?? 0)} / ${
                        downloadProgress && downloadProgress.total_bytes > 0
                          ? formatMib(downloadProgress.total_bytes)
                          : '?'
                      }`
                    : `${t('report.evalRunning')} (${progress.completed} / ${progress.total})`}
                </p>
                <div className="w-64 h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{
                      width: `${
                        evalStage === 'downloading' && downloadProgress && downloadProgress.total_bytes > 0
                          ? (downloadProgress.downloaded_bytes / downloadProgress.total_bytes) * 100
                          : progress.total > 0
                            ? (progress.completed / progress.total) * 100
                            : 0
                      }%`,
                    }}
                  />
                </div>
              </div>
            ) : report ? (
              <div className="space-y-6 max-w-4xl mx-auto">
                <div className="grid grid-cols-4 gap-4">
                  <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
                    <span className="text-sm text-muted-foreground">{t('report.totalCases')}</span>
                    <span className="text-3xl font-bold mt-1">{report.total}</span>
                  </div>
                  <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
                    <span className="text-sm text-muted-foreground">{t('report.passRate')}</span>
                    <span
                      className={`text-3xl font-bold mt-1 ${successRate >= 80 ? 'text-green-500' : 'text-amber-500'}`}
                    >
                      {successRate}%
                    </span>
                  </div>
                  <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
                    <span className="text-sm text-muted-foreground">{t('report.avgTime')}</span>
                    <span className="text-3xl font-bold mt-1">
                      {report.avg_time_secs ? report.avg_time_secs.toFixed(2) : '-'}s
                    </span>
                  </div>
                  <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
                    <span className="text-sm text-muted-foreground">{t('report.avgToken')}</span>
                    <span className="text-3xl font-bold mt-1">{Math.round(report.avg_total_tokens || 0)}</span>
                  </div>
                </div>

                {report.manifest && (
                  <div className="border rounded-lg p-4 bg-muted/10">
                    <h3 className="text-sm font-medium text-muted-foreground mb-3">{t('report.environment')}</h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                      <div>
                        <span className="text-muted-foreground">{t('report.envModel')}</span>
                        <p className="font-mono text-xs mt-0.5">
                          {report.manifest.model_provider}/{report.manifest.model_id}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envThinking')}</span>
                        <p className="font-mono text-xs mt-0.5">{report.manifest.thinking_effort}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envVersion')}</span>
                        <p className="font-mono text-xs mt-0.5">{report.manifest.harness_version}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envTools')}</span>
                        <p
                          className="font-mono text-xs mt-0.5 truncate"
                          title={report.manifest.tool_policy?.join(', ')}
                        >
                          {report.manifest.tool_policy?.join(', ') || '-'}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envDataset')}</span>
                        <p className="font-mono text-xs mt-0.5">{report.manifest.task_set_id}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envPrompt')}</span>
                        <p className="font-mono text-xs mt-0.5" title={report.manifest.prompt_fingerprint}>
                          {report.manifest.prompt_fingerprint?.slice(0, 12)}...
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envProfile')}</span>
                        <p className="font-mono text-xs mt-0.5">{report.manifest.profile_id || '-'}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t('report.envBenchmark')}</span>
                        <p className="font-mono text-xs mt-0.5">{report.manifest.benchmark_mode ? 'ON' : 'OFF'}</p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="space-y-3">
                  <h3 className="text-lg font-medium">{t('report.executionDetails')}</h3>
                  <div className="border rounded-lg overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-muted/50 border-b">
                        <tr>
                          <th className="px-4 py-3 font-medium">{t('report.status')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.messageSnippet')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.tokenUsage')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.duration')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.actions')}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {report.cases &&
                          report.cases.map((c, i: number) => (
                            <tr key={i} className="bg-card hover:bg-muted/20 transition-colors">
                              <td className="px-4 py-3">
                                {c.passed === true ? (
                                  <span className="flex items-center gap-1 text-green-600">
                                    <CheckCircle2 className="w-4 h-4" />
                                    {t('report.passed')}
                                  </span>
                                ) : c.passed === false ? (
                                  <span className="flex items-center gap-1 text-red-600">
                                    <XCircle className="w-4 h-4" />
                                    {t('report.failed')}
                                  </span>
                                ) : (
                                  <span className="flex items-center gap-1 text-muted-foreground">
                                    <Clock className="w-4 h-4" />
                                    {t('report.pending')}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 max-w-xs truncate" title={c.case?.message}>
                                {c.case?.message || t('report.multiTurn')}
                                {c.scores?.pass_rate != null && (
                                  <span
                                    className={`ml-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                                      c.scores.pass_rate >= 1
                                        ? 'bg-green-500/10 text-green-600'
                                        : 'bg-amber-500/10 text-amber-600'
                                    }`}
                                  >
                                    {c.scores.pass_rate >= 1
                                      ? '100%'
                                      : `${Math.min(99, Math.floor(c.scores.pass_rate * 100))}%`}
                                    {c.scores.tests_total != null &&
                                      ` · ${c.scores.tests_passed ?? 0}/${c.scores.tests_total}`}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3">{c.usage?.total_tokens || 0}</td>
                              <td className="px-4 py-3">{c.time_secs ? c.time_secs.toFixed(2) : '-'}s</td>
                              <td className="px-4 py-3">
                                {c.details ? (
                                  <div className="flex flex-col items-start gap-1">
                                    <p
                                      className="max-w-[320px] truncate text-xs text-muted-foreground"
                                      title={String(c.details)}
                                    >
                                      {String(c.details)}
                                    </p>
                                    <button
                                      onClick={() => {
                                        const expected = {
                                          tools: c.case?.expected_tools || [],
                                          output: c.case?.state_assertions?.length
                                            ? c.case.state_assertions
                                            : undefined,
                                        };
                                        const actual = {
                                          tools: c.actual_tools || [],
                                          output: c.actual_output || '',
                                        };
                                        viewDiff(JSON.stringify(expected, null, 2), JSON.stringify(actual, null, 2));
                                      }}
                                      className="flex items-center gap-1 text-primary hover:underline"
                                    >
                                      <Eye className="w-4 h-4" /> {t('report.viewDiff')}
                                    </button>
                                  </div>
                                ) : null}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <AlertCircle className="w-12 h-12 opacity-20" />
                <p>{t('report.noReport')}</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="matrix" className="h-full p-6 overflow-y-auto">
            {matrixRunning ? (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <RefreshCw className="w-8 h-8 animate-spin text-primary" />
                <p>
                  {t('matrix.running')} — {matrixProgress.current_profile || '...'}
                </p>
                <p className="text-sm">
                  {t('matrix.profileProgress')}: {matrixProgress.profile_progress}/{matrixProgress.profile_total} |{' '}
                  {t('matrix.caseProgress')}: {matrixProgress.case_completed}/{matrixProgress.case_total}
                </p>
                <div className="w-64 h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{
                      width: `${matrixProgress.case_total > 0 ? (matrixProgress.case_completed / matrixProgress.case_total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            ) : matrixReport ? (
              <MatrixResultView
                report={matrixReport}
                profileNames={Object.fromEntries(profiles.map((p) => [p.agent_id, p.name || p.agent_id.slice(0, 8)]))}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <Grid3X3 className="w-12 h-12 opacity-20" />
                <p>{t('matrix.noReport')}</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="memory-ab" className="h-full p-6 overflow-y-auto">
            {memoryAbRunning ? (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <RefreshCw className="w-8 h-8 animate-spin text-primary" />
                <p>
                  {memoryAbProgress.stage === 'downloading'
                    ? `${t('wbBench.downloading')}: ${formatMib(memoryAbProgress.download_progress?.downloaded_bytes ?? 0)} / ${
                        memoryAbProgress.download_progress && memoryAbProgress.download_progress.total_bytes > 0
                          ? formatMib(memoryAbProgress.download_progress.total_bytes)
                          : '?'
                      }`
                    : `${t('memoryAb.running')} — ${memoryAbProgress.current_arm || '...'}`}
                </p>
                <p className="text-sm">
                  {t('matrix.profileProgress')}: {memoryAbProgress.profile_progress}/{memoryAbProgress.profile_total} |{' '}
                  {t('matrix.caseProgress')}: {memoryAbProgress.case_completed}/{memoryAbProgress.case_total}
                </p>
                <div className="w-64 h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{
                      width: `${memoryAbProgress.case_total > 0 ? (memoryAbProgress.case_completed / memoryAbProgress.case_total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            ) : memoryAbReport ? (
              <div className="space-y-6 max-w-5xl mx-auto">
                <MatrixResultView report={memoryAbReport} profileNames={memoryAbProfileNames()} />
                <MemoryAbHistoryTable
                  items={memoryAbHistory}
                  selectedTimestamp={selectedMemoryAbTs}
                  onSelect={loadMemoryAbReport}
                />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <BrainCircuit className="w-12 h-12 opacity-20" />
                <p>{t('memoryAb.noReport')}</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="history" className="h-full p-6 overflow-y-auto">
            {history.length > 0 ? (
              <div className="space-y-6 max-w-4xl mx-auto">
                <div className="border rounded-lg p-4 bg-card h-[300px]">
                  <h3 className="text-sm font-medium mb-4 text-muted-foreground">{t('history.passRateTrend')}</h3>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={history} margin={{ top: 5, right: 20, bottom: 25, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis
                        dataKey={(d: ReportItem) =>
                          d.timestamp ? new Date(d.timestamp * 1000).toLocaleTimeString() : ''
                        }
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                      <RechartsTooltip
                        labelFormatter={(l: string) => `${t('history.time')}: ${l}`}
                        formatter={(val: number) => [`${Math.round(val)}%`, t('history.passRateLabel')]}
                      />
                      <Line
                        type="monotone"
                        dataKey={(d: ReportItem) => (d.total && d.passed != null ? (d.passed / d.total) * 100 : 0)}
                        stroke="#10b981"
                        strokeWidth={2}
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="space-y-3">
                  <h3 className="text-lg font-medium">{t('history.historyRecords')}</h3>
                  <div className="border rounded-lg overflow-x-auto">
                    <table className="w-full text-sm text-left min-w-[700px]">
                      <thead className="bg-muted/50 border-b">
                        <tr>
                          <th className="px-4 py-3 font-medium">{t('history.time')}</th>
                          <th className="px-4 py-3 font-medium">{t('history.profile')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.envModel')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.totalCases')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.passRate')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.avgTime')}</th>
                          <th className="px-4 py-3 font-medium">{t('report.avgToken')}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {history
                          .slice()
                          .reverse()
                          .map((h: ReportItem, i: number) => {
                            const total = h.total ?? 0;
                            const passed = h.passed ?? 0;
                            const rate = total > 0 ? Math.round((passed / total) * 100) : 0;
                            const m = h.manifest;
                            return (
                              <tr
                                key={i}
                                className={`bg-card hover:bg-muted/20 transition-colors cursor-pointer ${loadingReport === h.filename ? 'opacity-60' : ''}`}
                                onClick={async () => {
                                  if (!h.filename || loadingReport) return;
                                  setLoadingReport(h.filename);
                                  try {
                                    const res = await fetch(`/api/v1/eval/reports/${h.filename}`);
                                    const data = await res.json();
                                    if (data.status === 'success' && data.summary) {
                                      setReport(data.summary);
                                      setActiveTab('report');
                                    }
                                  } catch {
                                    toast.error(t('loadReportFailed'));
                                  } finally {
                                    setLoadingReport(null);
                                  }
                                }}
                              >
                                <td className="px-4 py-3 flex items-center gap-2">
                                  {loadingReport === h.filename && (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
                                  )}
                                  {h.timestamp ? new Date(h.timestamp * 1000).toLocaleString() : '-'}
                                </td>
                                <td className="px-4 py-3">
                                  <span className="font-mono text-xs">{m?.profile_id || '-'}</span>
                                  {m?.benchmark_mode && (
                                    <span className="ml-1 px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 rounded">
                                      BM
                                    </span>
                                  )}
                                </td>
                                <td className="px-4 py-3 font-mono text-xs">
                                  {m ? `${m.model_provider}/${m.model_id}` : '-'}
                                </td>
                                <td className="px-4 py-3">{h.total}</td>
                                <td
                                  className={`px-4 py-3 font-medium ${rate >= 80 ? 'text-green-500' : 'text-amber-500'}`}
                                >
                                  {rate}%
                                </td>
                                <td className="px-4 py-3">{h.avg_time_secs ? h.avg_time_secs.toFixed(2) : '-'}s</td>
                                <td className="px-4 py-3">{Math.round(h.avg_total_tokens || 0)}</td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <AlertCircle className="w-12 h-12 opacity-20" />
                <p>{t('history.noHistory')}</p>
              </div>
            )}
          </TabsContent>

          {diffView && (
            <TabsContent value="diff" className="h-full p-0 m-0">
              <DiffEditor
                height="100%"
                theme="vs-dark"
                original={diffView.expected}
                modified={diffView.actual}
                options={{ readOnly: true, minimap: { enabled: false } }}
              />
            </TabsContent>
          )}
        </Tabs>
      </div>

      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>{t('createDataset')}</DialogTitle>
          </DialogHeader>
          <Input
            ref={createInputRef}
            value={newDatasetName}
            onChange={(e) => setNewDatasetName(e.target.value)}
            placeholder={t('createDatasetPrompt')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreateDataset();
            }}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={handleCreateDataset} disabled={!newDatasetName.trim()}>
              {t('create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

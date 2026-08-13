import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

export interface EvalDataset {
  id: string;
  filename?: string;
  updated_at?: number;
  size?: number;
}

export interface EvalProfile {
  agent_id: string;
  name: string;
}

export interface ReportItem {
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
    judge_model?: string;
    max_tool_calls?: number;
    max_iterations?: number;
  };
  decontam_active?: boolean;
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

export interface EvalProgress {
  total: number;
  completed: number;
}

export interface DownloadProgress {
  downloaded_bytes: number;
  total_bytes: number;
}

export interface CasesEval {
  cases: string;
  casesDraft: string;
  setCasesDraft: (value: string) => void;
  saving: boolean;
  running: boolean;
  progress: EvalProgress;
  evalStage: string | null;
  evalStageSubsetId: string | null;
  downloadProgress: DownloadProgress | null;
  sourcesRefreshToken: number;
  report: ReportItem | null;
  history: ReportItem[];
  loadingReport: string | null;
  diffView: { expected: string; actual: string } | null;
  ready: boolean;
  startRun: (profileId: string | null, datasetId: string, benchmarkMode: boolean, onStarted?: () => void) => Promise<void>;
  startBenchmark: (
    benchmarkId: string,
    profileId: string | null,
    benchmarkMode: boolean,
    limit: number | undefined,
    onStarted?: () => void,
  ) => Promise<void>;
  startDownload: (benchmarkId: string, onStarted?: () => void) => Promise<void>;
  abort: () => Promise<void>;
  saveDraft: (datasetId: string) => Promise<void>;
  loadHistoryReport: (filename: string) => Promise<boolean>;
  openDiff: (expected: string, actual: string) => void;
}

export function useCasesEval(selectedDatasetId: string): CasesEval {
  const t = useTranslations('evalLab');
  const [cases, setCases] = useState('');
  const [casesDraft, setCasesDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<EvalProgress>({ total: 0, completed: 0 });
  const [evalStage, setEvalStage] = useState<string | null>(null);
  const [evalStageSubsetId, setEvalStageSubsetId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [sourcesRefreshToken, setSourcesRefreshToken] = useState(0);
  const [report, setReport] = useState<ReportItem | null>(null);
  const [history, setHistory] = useState<ReportItem[]>([]);
  const [loadingReport, setLoadingReport] = useState<string | null>(null);
  const [diffView, setDiffView] = useState<{ expected: string; actual: string } | null>(null);
  const [ready, setReady] = useState(false);

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
  }, [running, fetchReport]);

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

  useEffect(() => {
    Promise.all([fetchStatus(), fetchReport(), fetchHistory()]).finally(() => setReady(true));
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
      // Fast tasks (e.g. a cached-archive download) can finish before the
      // EventSource connects, making the stream EOF immediately and firing
      // onerror instead of onmessage. Both paths converge here so the UI
      // always re-pulls the report and sources after a completed run.
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
        finalize();
      };
    }
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [running, fetchReport, fetchHistory]);

  const startRun = useCallback(
    async (profileId: string | null, datasetId: string, benchmarkMode: boolean, onStarted?: () => void) => {
      try {
        const res = await fetch('/api/v1/eval/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            profile_id: profileId,
            dataset_id: datasetId,
            benchmark_mode: benchmarkMode,
          }),
        });
        const data = await res.json();
        if (data.status === 'started' || data.status === 'already_running') {
          setRunning(true);
          toast.success(t('evalStarted'));
          onStarted?.();
        }
      } catch {
        toast.error(t('evalStartFailed'));
      }
    },
    [t],
  );

  const startBenchmark = useCallback(
    async (
      benchmarkId: string,
      profileId: string | null,
      benchmarkMode: boolean,
      limit: number | undefined,
      onStarted?: () => void,
    ) => {
      try {
        const res = await fetch('/api/v1/eval/benchmarks/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            benchmark_id: benchmarkId,
            profile_id: profileId,
            benchmark_mode: benchmarkMode,
            ...(limit !== undefined ? { limit } : {}),
          }),
        });
        const data = await res.json();
        if (data.status === 'started') {
          setRunning(true);
          toast.success(t('benchmarksRunStarted'));
          onStarted?.();
        } else if (data.status === 'already_running') {
          toast.info(t('alreadyRunning'));
        } else {
          toast.error(data.error || t('evalStartFailed'));
        }
      } catch {
        toast.error(t('evalStartFailed'));
      }
    },
    [t],
  );

  const startDownload = useCallback(
    async (benchmarkId: string, onStarted?: () => void) => {
      try {
        const res = await fetch('/api/v1/eval/benchmarks/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ benchmark_id: benchmarkId }),
        });
        const data = await res.json();
        if (data.status === 'started') {
          setRunning(true);
          onStarted?.();
        } else if (data.status === 'already_running') {
          toast.info(t('alreadyRunning'));
        } else {
          toast.error(data.error || t('evalStartFailed'));
        }
      } catch {
        toast.error(t('evalStartFailed'));
      }
    },
    [t],
  );

  const abort = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/abort', { method: 'POST' });
      if (res.ok) {
        toast.success(t('abortSent'));
      }
    } catch {
      toast.error(t('abortFailed'));
    }
  }, [t]);

  const saveDraft = useCallback(
    async (datasetId: string) => {
      setSaving(true);
      try {
        const res = await fetch(`/api/v1/eval/datasets/${datasetId}`, {
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
    },
    [casesDraft, t],
  );

  const loadHistoryReport = useCallback(
    async (filename: string) => {
      setLoadingReport(filename);
      try {
        const res = await fetch(`/api/v1/eval/reports/${filename}`);
        const data = await res.json();
        if (data.status === 'success' && data.summary) {
          setReport(data.summary);
          return true;
        }
        return false;
      } catch {
        toast.error(t('loadReportFailed'));
        return false;
      } finally {
        setLoadingReport(null);
      }
    },
    [t],
  );

  const openDiff = useCallback((expected: string, actual: string) => {
    setDiffView({ expected, actual });
  }, []);

  return {
    cases,
    casesDraft,
    setCasesDraft,
    saving,
    running,
    progress,
    evalStage,
    evalStageSubsetId,
    downloadProgress,
    sourcesRefreshToken,
    report,
    history,
    loadingReport,
    diffView,
    ready,
    startRun,
    startBenchmark,
    startDownload,
    abort,
    saveDraft,
    loadHistoryReport,
    openDiff,
  };
}

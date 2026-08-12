import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { type MatrixReportData } from '../components/MatrixResultView';
import { type MemoryAbHistoryItem } from '../components/MemoryAbHistoryTable';

export interface MemoryAbProgress {
  current_arm: string;
  stage: string;
  profile_progress: number;
  profile_total: number;
  case_completed: number;
  case_total: number;
  download_progress: { downloaded_bytes: number; total_bytes: number } | null;
}

export interface MemoryAbEval {
  memoryAbReport: MatrixReportData | null;
  memoryAbRunning: boolean;
  memoryAbProgress: MemoryAbProgress;
  memoryAbHistory: MemoryAbHistoryItem[];
  selectedMemoryAbTs: number | null;
  ready: boolean;
  start: (
    benchmarkId: string,
    profileId: string | null,
    limit: number | undefined,
    onStarted?: () => void,
  ) => Promise<void>;
  abort: () => Promise<void>;
  loadReport: (timestamp: number) => Promise<void>;
}

const emptyProgress: MemoryAbProgress = {
  current_arm: '',
  stage: '',
  profile_progress: 0,
  profile_total: 0,
  case_completed: 0,
  case_total: 0,
  download_progress: null,
};

export function useMemoryAbEval(): MemoryAbEval {
  const t = useTranslations('evalLab');
  const [memoryAbReport, setMemoryAbReport] = useState<MatrixReportData | null>(null);
  const [memoryAbRunning, setMemoryAbRunning] = useState(false);
  const [memoryAbProgress, setMemoryAbProgress] = useState<MemoryAbProgress>(emptyProgress);
  const [memoryAbHistory, setMemoryAbHistory] = useState<MemoryAbHistoryItem[]>([]);
  const [selectedMemoryAbTs, setSelectedMemoryAbTs] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

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

  useEffect(() => {
    Promise.all([fetchMemoryAbReport(), fetchMemoryAbHistory()]).finally(() => setReady(true));
  }, [fetchMemoryAbReport, fetchMemoryAbHistory]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    if (memoryAbRunning) {
      eventSource = new EventSource('/api/v1/eval/memory-ab/stream');

      let finalized = false;
      // A fast run can finish before the EventSource connects, making the
      // stream EOF immediately and firing onerror instead of onmessage.
      // Both paths converge here so the UI never shows stale state.
      const finalize = () => {
        if (finalized) return;
        finalized = true;
        eventSource?.close();
        setMemoryAbRunning(false);
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
        finalize();
      };
    }
    return () => {
      eventSource?.close();
    };
  }, [memoryAbRunning, fetchMemoryAbReport, fetchMemoryAbHistory]);

  const start = useCallback(
    async (benchmarkId: string, profileId: string | null, limit: number | undefined, onStarted?: () => void) => {
      try {
        const res = await fetch('/api/v1/eval/memory-ab/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            benchmark_id: benchmarkId,
            profile_id: profileId,
            ...(limit !== undefined ? { limit } : {}),
          }),
        });
        const data = await res.json();
        if (data.status === 'started') {
          setMemoryAbRunning(true);
          toast.success(t('memoryAb.started'));
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
      const res = await fetch('/api/v1/eval/memory-ab/abort', { method: 'POST' });
      if (res.ok) {
        toast.success(t('abortSent'));
      }
    } catch {
      toast.error(t('abortFailed'));
    }
  }, [t]);

  const loadReport = useCallback(
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

  return {
    memoryAbReport,
    memoryAbRunning,
    memoryAbProgress,
    memoryAbHistory,
    selectedMemoryAbTs,
    ready,
    start,
    abort,
    loadReport,
  };
}

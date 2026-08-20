import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { type MatrixReportData } from '../components/MatrixResultView';
import { type MatrixHistoryItem } from '../components/MatrixHistoryTable';

export interface MatrixProgress {
  current_profile: string;
  stage: string;
  profile_progress: number;
  profile_total: number;
  case_completed: number;
  case_total: number;
  download_progress: { downloaded_bytes: number; total_bytes: number } | null;
}

export interface MatrixEval {
  matrixReport: MatrixReportData | null;
  matrixRunning: boolean;
  matrixProgress: MatrixProgress;
  matrixHistory: MatrixHistoryItem[];
  selectedMatrixTs: number | null;
  ready: boolean;
  startMatrix: (
    profileIds: string[],
    datasetId: string,
    benchmarkMode: boolean,
    onStarted?: () => void,
  ) => Promise<void>;
  startLayer: (
    benchmarkId: string,
    profileId: string | null,
    limit: number | undefined,
    onStarted?: () => void,
  ) => Promise<void>;
  abort: () => Promise<void>;
  loadReport: (timestamp: number) => Promise<void>;
}

const emptyProgress: MatrixProgress = {
  current_profile: '',
  stage: '',
  profile_progress: 0,
  profile_total: 0,
  case_completed: 0,
  case_total: 0,
  download_progress: null,
};

export function useMatrixEval(): MatrixEval {
  const t = useTranslations('evalLab');
  const [matrixReport, setMatrixReport] = useState<MatrixReportData | null>(null);
  const [matrixRunning, setMatrixRunning] = useState(false);
  const [matrixProgress, setMatrixProgress] = useState<MatrixProgress>(emptyProgress);
  const [matrixHistory, setMatrixHistory] = useState<MatrixHistoryItem[]>([]);
  const [selectedMatrixTs, setSelectedMatrixTs] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

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

  const fetchMatrixHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/matrix/reports/history');
      const data = await res.json();
      if (data.status === 'success' && Array.isArray(data.reports)) {
        setMatrixHistory(data.reports as MatrixHistoryItem[]);
      }
    } catch (e) {
      console.error('Failed to fetch matrix history:', e);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchMatrixReport(), fetchMatrixHistory()]).finally(() => setReady(true));
  }, [fetchMatrixReport, fetchMatrixHistory]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    if (matrixRunning) {
      eventSource = new EventSource('/api/v1/eval/matrix/stream');

      let finalized = false;
      // Fast tasks can finish before the EventSource connects, making the
      // stream EOF immediately and firing onerror instead of onmessage.
      // Both paths converge here so the UI always re-pulls fresh results.
      const finalize = () => {
        if (finalized) {
          return;
        }
        finalized = true;
        eventSource?.close();
        setMatrixRunning(false);
        setSelectedMatrixTs(null);
        fetchMatrixReport();
        fetchMatrixHistory();
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMatrixRunning(!!data.is_running);
          setMatrixProgress({
            current_profile: data.current_profile || '',
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
          console.error('Matrix SSE parse error', e);
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
  }, [matrixRunning, fetchMatrixReport, fetchMatrixHistory]);

  const startMatrix = useCallback(
    async (profileIds: string[], datasetId: string, benchmarkMode: boolean, onStarted?: () => void) => {
      try {
        const res = await fetch('/api/v1/eval/matrix/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            profile_ids: profileIds,
            dataset_id: datasetId,
            benchmark_mode: benchmarkMode,
          }),
        });
        const data = await res.json();
        if (data.status === 'started' || data.status === 'already_running') {
          setMatrixRunning(true);
          toast.success(t('matrixEvalStarted'));
          onStarted?.();
        }
      } catch {
        toast.error(t('evalStartFailed'));
      }
    },
    [t],
  );

  const startLayer = useCallback(
    async (benchmarkId: string, profileId: string | null, limit: number | undefined, onStarted?: () => void) => {
      try {
        const res = await fetch('/api/v1/eval/matrix/layers-run', {
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
          setMatrixRunning(true);
          toast.success(t('layers.started'));
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
      const res = await fetch('/api/v1/eval/matrix/abort', { method: 'POST' });
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
        const res = await fetch(`/api/v1/eval/matrix/reports/${timestamp}`);
        const data = (await res.json()) as { status?: string; report?: MatrixReportData | null };
        if (data.status === 'success' && data.report) {
          setMatrixReport(data.report);
          setSelectedMatrixTs(timestamp);
        } else {
          toast.error(t('loadReportFailed'));
        }
      } catch (e) {
        console.error('Failed to fetch matrix report:', e);
        toast.error(t('loadReportFailed'));
      }
    },
    [t],
  );

  return {
    matrixReport,
    matrixRunning,
    matrixProgress,
    matrixHistory,
    selectedMatrixTs,
    ready,
    startMatrix,
    startLayer,
    abort,
    loadReport,
  };
}

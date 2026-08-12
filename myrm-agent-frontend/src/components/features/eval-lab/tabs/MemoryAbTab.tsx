import { useTranslations } from 'next-intl';
import { BrainCircuit } from 'lucide-react';

import MatrixResultView, { type MatrixReportData } from '../MatrixResultView';
import MemoryAbHistoryTable, { type MemoryAbHistoryItem } from '../MemoryAbHistoryTable';
import EvalRunProgress from './EvalRunProgress';
import { type MemoryAbProgress } from '../hooks/useMemoryAbEval';

interface MemoryAbTabProps {
  running: boolean;
  progress: MemoryAbProgress;
  report: MatrixReportData | null;
  history: MemoryAbHistoryItem[];
  selectedTimestamp: number | null;
  armNames: { memory_off: string; memory_on: string };
  onLoadReport: (timestamp: number) => void;
}

export default function MemoryAbTab({
  running,
  progress,
  report,
  history,
  selectedTimestamp,
  armNames,
  onLoadReport,
}: MemoryAbTabProps) {
  const t = useTranslations('evalLab');

  if (running) {
    return (
      <EvalRunProgress
        stage={progress.stage}
        title={`${t('memoryAb.running')} — ${progress.current_arm || '...'}`}
        profileProgress={progress.profile_progress}
        profileTotal={progress.profile_total}
        caseCompleted={progress.case_completed}
        caseTotal={progress.case_total}
        downloadProgress={progress.download_progress}
      />
    );
  }

  if (report) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <MatrixResultView report={report} profileNames={armNames} />
        <MemoryAbHistoryTable items={history} selectedTimestamp={selectedTimestamp} onSelect={onLoadReport} />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
      <BrainCircuit className="w-12 h-12 opacity-20" />
      <p>{t('memoryAb.noReport')}</p>
    </div>
  );
}

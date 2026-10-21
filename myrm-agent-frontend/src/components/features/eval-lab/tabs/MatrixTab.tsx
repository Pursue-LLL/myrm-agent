import { useTranslations } from 'next-intl';
import { Grid3X3 } from 'lucide-react';

import MatrixResultView, { type MatrixReportData } from '../components/MatrixResultView';
import MatrixHistoryTable, { type MatrixHistoryItem } from '../components/MatrixHistoryTable';
import EvalRunProgress from './EvalRunProgress';
import { type MatrixProgress } from '../hooks/useMatrixEval';

interface MatrixTabProps {
  running: boolean;
  progress: MatrixProgress;
  report: MatrixReportData | null;
  history: MatrixHistoryItem[];
  selectedTimestamp: number | null;
  profileNames: Record<string, string>;
  onLoadReport: (timestamp: number) => void;
}

export default function MatrixTab({
  running,
  progress,
  report,
  history,
  selectedTimestamp,
  profileNames,
  onLoadReport,
}: MatrixTabProps) {
  const t = useTranslations('evalLab');

  if (running) {
    return (
      <EvalRunProgress
        stage={progress.stage}
        title={`${t('matrix.running')} — ${progress.current_profile || '...'}`}
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
        <MatrixResultView report={report} profileNames={profileNames} />
        <MatrixHistoryTable items={history} selectedTimestamp={selectedTimestamp} onSelect={onLoadReport} />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
      <Grid3X3 className="w-12 h-12 opacity-20" />
      <p>{t('matrix.noReport')}</p>
    </div>
  );
}

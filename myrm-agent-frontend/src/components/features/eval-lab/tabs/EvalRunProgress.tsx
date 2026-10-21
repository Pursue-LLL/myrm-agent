import { useTranslations } from 'next-intl';
import { RefreshCw } from 'lucide-react';

import { formatMib } from '../components/format';

interface EvalRunProgressProps {
  stage: string;
  title: string;
  profileProgress: number;
  profileTotal: number;
  caseCompleted: number;
  caseTotal: number;
  downloadProgress: { downloaded_bytes: number; total_bytes: number } | null;
}

export default function EvalRunProgress({
  stage,
  title,
  profileProgress,
  profileTotal,
  caseCompleted,
  caseTotal,
  downloadProgress,
}: EvalRunProgressProps) {
  const t = useTranslations('evalLab');

  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
      <RefreshCw className="w-8 h-8 animate-spin text-primary" />
      <p>
        {stage === 'downloading'
          ? `${t('wbBench.downloading')}: ${formatMib(downloadProgress?.downloaded_bytes ?? 0)} / ${
              downloadProgress && downloadProgress.total_bytes > 0 ? formatMib(downloadProgress.total_bytes) : '?'
            }`
          : title}
      </p>
      <p className="text-sm">
        {t('matrix.profileProgress')}: {profileProgress}/{profileTotal} | {t('matrix.caseProgress')}: {caseCompleted}/
        {caseTotal}
      </p>
      <div className="w-64 h-2 bg-secondary rounded-full overflow-hidden">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${caseTotal > 0 ? (caseCompleted / caseTotal) * 100 : 0}%` }}
        />
      </div>
    </div>
  );
}

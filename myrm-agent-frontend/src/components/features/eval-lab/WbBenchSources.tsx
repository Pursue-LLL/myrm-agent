import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Database, DownloadCloud, HardDrive, Play, RefreshCw, Boxes, BrainCircuit, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';

interface WbBenchSource {
  id: string;
  name: string;
  task_count: number;
  approx_size_mb: number;
  is_downloaded: boolean;
  local_size_bytes: number;
  scoring?: string;
}

interface ReportItem {
  timestamp?: number;
  total_cases?: number;
  pass_count?: number;
  skip_count?: number;
  pass_rate?: number;
  avg_pass_rate?: number;
  manifest?: {
    task_set_id?: string;
  };
}

interface Props {
  running: boolean;
  history: ReportItem[];
  onRun: (subsetId: string) => void;
  onDownload: (subsetId: string) => void;
  onMemoryAb: (subsetId: string) => void;
  refreshToken: number;
  downloadingSubsetId: string | null;
  downloadProgress: { downloaded_bytes: number; total_bytes: number } | null;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** idx).toFixed(1)} ${units[idx]}`;
}

export default function WbBenchSources({
  running,
  history,
  onRun,
  onDownload,
  onMemoryAb,
  refreshToken,
  downloadingSubsetId,
  downloadProgress,
}: Props) {
  const t = useTranslations('evalLab.wbBench');
  const tMemoryAb = useTranslations('evalLab.memoryAb');
  const [sources, setSources] = useState<WbBenchSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingMemoryAbSubset, setPendingMemoryAbSubset] = useState<string | null>(null);

  const fetchSources = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/wb-bench/sources');
      const data = await res.json();
      if (data.status === 'success' && Array.isArray(data.sources)) {
        setSources(data.sources);
      }
    } catch (e) {
      console.error('Failed to fetch WBBench sources:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
  }, [fetchSources, refreshToken]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchSources();
    setRefreshing(false);
  };

  const latestReportFor = (subsetId: string): ReportItem | null => {
    const matches = history.filter((h) => h?.manifest?.task_set_id === `wb-bench-${subsetId}`);
    return matches.length > 0 ? matches[matches.length - 1] : null;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold">{t('title')}</h3>
              <p className="text-sm text-muted-foreground mt-0.5 max-w-2xl">{t('description')}</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sources.map((source) => {
            const report = latestReportFor(source.id);
            const downloadingThis = running && downloadingSubsetId === source.id;
            const downloadPct =
              downloadingThis && downloadProgress && downloadProgress.total_bytes > 0
                ? Math.min(100, (downloadProgress.downloaded_bytes / downloadProgress.total_bytes) * 100)
                : 0;
            const isScored =
              report != null &&
              report.total_cases != null &&
              (report.skip_count ?? 0) < report.total_cases;
            const passRate =
              report && report.total_cases && report.pass_count != null && isScored
                ? Math.round((report.pass_count / report.total_cases) * 100)
                : null;
            const testPassRate =
              report?.avg_pass_rate != null && isScored ? Math.round(report.avg_pass_rate * 100) : null;
            return (
              <Card key={source.id} className="flex flex-col">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Boxes className="w-4 h-4 text-muted-foreground" />
                      {source.name}
                    </CardTitle>
                    <div className="flex items-center gap-1.5">
                      <Badge
                        variant="secondary"
                        className="bg-primary/10 text-primary"
                        title={source.scoring === 'native' ? t('scoringNativeTitle') : t('scoringCompositeTitle')}
                      >
                        {source.scoring === 'native' ? t('scoringNative') : t('scoringComposite')}
                      </Badge>
                      {source.is_downloaded ? (
                        <Badge variant="secondary" className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                          {t('downloaded')}
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="bg-amber-500/10 text-amber-600 dark:text-amber-400">
                          {t('notDownloaded')}
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="flex-1 flex flex-col gap-4">
                  <div className="grid grid-cols-3 gap-3 text-sm">
                    <div className="flex flex-col">
                      <span className="text-muted-foreground text-xs">{t('taskCount')}</span>
                      <span className="font-semibold mt-0.5">{source.task_count}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-muted-foreground text-xs">{t('approxSize')}</span>
                      <span className="font-semibold mt-0.5">{source.approx_size_mb} MB</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-muted-foreground text-xs">{t('localSize')}</span>
                      <span className="font-semibold mt-0.5 flex items-center gap-1">
                        <HardDrive className="w-3.5 h-3.5 text-muted-foreground" />
                        {source.is_downloaded ? formatBytes(source.local_size_bytes) : '-'}
                      </span>
                    </div>
                  </div>

                  {report ? (
                    <div className="rounded-lg border bg-muted/20 px-3 py-2 text-sm">
                      <div className="flex items-center justify-between text-muted-foreground text-xs">
                        <span>{t('lastReport')}</span>
                        {report.timestamp ? new Date(report.timestamp * 1000).toLocaleString() : ''}
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <span className="text-xs text-muted-foreground">
                          {t('reportTotal')}: {report.total_cases ?? 0}
                        </span>
                        {passRate !== null ? (
                          <span className={`font-semibold ${passRate >= 80 ? 'text-emerald-500' : 'text-amber-500'}`}>
                            {passRate}%
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">{t('pendingScoring')}</span>
                        )}
                      </div>
                      {testPassRate !== null && (
                        <div className="flex items-center justify-between mt-0.5 text-xs">
                          <span className="text-muted-foreground">{t('testPassRate')}</span>
                          <span className={`font-medium ${testPassRate >= 80 ? 'text-emerald-500' : 'text-amber-500'}`}>
                            {testPassRate}%
                          </span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground text-center">
                      {t('noReport')}
                    </div>
                  )}

                  {downloadingThis && downloadProgress && (
                    <div className="space-y-1.5">
                      <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div className="h-full bg-primary transition-all duration-300" style={{ width: `${downloadPct}%` }} />
                      </div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <DownloadCloud className="w-3.5 h-3.5 animate-pulse" />
                          {t('downloading')}
                        </span>
                        <span>
                          {formatBytes(downloadProgress.downloaded_bytes)} /{' '}
                          {downloadProgress.total_bytes > 0 ? formatBytes(downloadProgress.total_bytes) : '?'}
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-between gap-2 mt-auto flex-wrap">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onDownload(source.id)}
                      disabled={running || source.is_downloaded}
                      className="flex-1 min-w-[96px]"
                    >
                      <DownloadCloud className="w-4 h-4" />
                      {source.is_downloaded ? t('downloaded') : downloadingThis ? t('downloading') : t('download')}
                    </Button>
                    <Button size="sm" onClick={() => onRun(source.id)} disabled={running} className="flex-1 min-w-[96px]">
                      <Play className="w-4 h-4" />
                      {running ? t('running') : t('run')}
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setPendingMemoryAbSubset(source.id)}
                      disabled={running}
                      className="flex-1 min-w-[96px]"
                    >
                      <BrainCircuit className="w-4 h-4" />
                      {t('memoryAb')}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      <Dialog
        open={pendingMemoryAbSubset != null}
        onOpenChange={(open) => !open && setPendingMemoryAbSubset(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              {tMemoryAb('confirmTitle')}
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">{tMemoryAb('confirmBody')}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingMemoryAbSubset(null)}>
              {tMemoryAb('confirmCancel')}
            </Button>
            <Button
              onClick={() => {
                const subsetId = pendingMemoryAbSubset;
                setPendingMemoryAbSubset(null);
                if (subsetId) onMemoryAb(subsetId);
              }}
            >
              {tMemoryAb('confirmStart')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

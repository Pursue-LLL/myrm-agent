import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Database,
  DownloadCloud,
  HardDrive,
  Play,
  RefreshCw,
  Boxes,
  BrainCircuit,
  AlertTriangle,
  Layers,
} from 'lucide-react';
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

interface BenchmarkSource {
  benchmark_id: string;
  name: string;
  description?: string;
  task_count: number;
  approx_size_mb: number;
  is_downloaded: boolean;
  local_size_bytes: number;
  scoring?: string;
  supports_memory_ab?: boolean;
  required_tools?: string[];
}

interface ReportItem {
  timestamp?: number;
  total_cases?: number;
  pass_count?: number;
  skip_count?: number;
  pass_rate?: number;
  avg_pass_rate?: number | null;
  manifest?: {
    task_set_id?: string;
    limit?: number;
  };
}

interface Props {
  running: boolean;
  history: ReportItem[];
  onRun: (benchmarkId: string, limit?: number) => void;
  onDownload: (benchmarkId: string) => void;
  onMemoryAb: (benchmarkId: string, limit?: number) => void;
  onLayerEval: (benchmarkId: string, limit?: number) => void;
  refreshToken: number;
  downloadingBenchmarkId: string | null;
  downloadProgress: { downloaded_bytes: number; total_bytes: number } | null;
  selectedProfileName?: string;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** idx).toFixed(1)} ${units[idx]}`;
}

function parseLimit(raw: string): number | undefined {
  if (raw.trim() === '') {
    return undefined;
  }
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.round(value) : undefined;
}

// Large benchmarks (e.g. BrowseComp with 1266 tasks) would take hours and
// cost a lot when run in full. Prefill a conservative default sample so a
// one-click run stays cheap; the user can still edit or clear it.
const LARGE_TASK_THRESHOLD = 100;
const DEFAULT_SAMPLE_SIZE = 20;

function defaultSampleSize(source: BenchmarkSource): string | null {
  return source.task_count > LARGE_TASK_THRESHOLD ? String(DEFAULT_SAMPLE_SIZE) : null;
}

function scoringLabel(source: BenchmarkSource, t: (key: string) => string): { label: string; title: string } {
  if (source.scoring === 'native') {
    return { label: t('scoringNative'), title: t('scoringNativeTitle') };
  }
  if (source.scoring === 'composite') {
    return { label: t('scoringComposite'), title: t('scoringCompositeTitle') };
  }
  return { label: t('scoringLlmsJudge'), title: t('scoringLlmsJudgeTitle') };
}

export default function BenchmarkSources({
  running,
  history,
  onRun,
  onDownload,
  onMemoryAb,
  onLayerEval,
  refreshToken,
  downloadingBenchmarkId,
  downloadProgress,
  selectedProfileName,
}: Props) {
  const t = useTranslations('evalLab.wbBench');
  const tMemoryAb = useTranslations('evalLab.memoryAb');
  const tLayers = useTranslations('evalLab.layers');
  const [sources, setSources] = useState<BenchmarkSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingMemoryAbBenchmark, setPendingMemoryAbBenchmark] = useState<string | null>(null);
  const [pendingMemoryAbLimit, setPendingMemoryAbLimit] = useState<number | undefined>(undefined);
  const [pendingLayerBenchmark, setPendingLayerBenchmark] = useState<string | null>(null);
  const [pendingLayerLimit, setPendingLayerLimit] = useState<number | undefined>(undefined);
  const [sampleLimits, setSampleLimits] = useState<Record<string, string>>({});

  const fetchSources = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/benchmarks');
      const data = await res.json();
      if (data.status === 'success' && Array.isArray(data.sources)) {
        setSources(data.sources);
        // Prefill a default sample for large benchmarks only when the user has
        // not entered anything for that card yet (clear = intentionally full).
        setSampleLimits((prev) => {
          const next = { ...prev };
          for (const source of data.sources as BenchmarkSource[]) {
            const prefilled = defaultSampleSize(source);
            if (prefilled != null && next[source.benchmark_id] == null) {
              next[source.benchmark_id] = prefilled;
            }
          }
          return next;
        });
      }
    } catch (e) {
      console.error('Failed to fetch benchmark sources:', e);
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

  const latestReportFor = (benchmarkId: string): ReportItem | null => {
    const matches = history.filter((h) => h?.manifest?.task_set_id === benchmarkId);
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
            const report = latestReportFor(source.benchmark_id);
            const downloadingThis = running && downloadingBenchmarkId === source.benchmark_id;
            const downloadPct =
              downloadingThis && downloadProgress && downloadProgress.total_bytes > 0
                ? Math.min(100, (downloadProgress.downloaded_bytes / downloadProgress.total_bytes) * 100)
                : 0;
            const isScored =
              report != null && report.total_cases != null && (report.skip_count ?? 0) < report.total_cases;
            const passRate =
              report && report.total_cases && report.pass_count != null && isScored
                ? Math.round((report.pass_count / report.total_cases) * 100)
                : null;
            const testPassRate =
              report?.avg_pass_rate != null && isScored ? Math.round(report.avg_pass_rate * 100) : null;
            const scoring = scoringLabel(source, (key) => t(key));
            return (
              <Card key={source.benchmark_id} className="flex flex-col">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Boxes className="w-4 h-4 text-muted-foreground" />
                      {source.name}
                    </CardTitle>
                    <div className="flex items-center gap-1.5">
                      <Badge variant="secondary" className="bg-primary/10 text-primary" title={scoring.title}>
                        {scoring.label}
                      </Badge>
                      {source.required_tools?.includes('web_search') && (
                        <Badge
                          variant="secondary"
                          className="bg-sky-500/10 text-sky-600 dark:text-sky-400"
                          title={t('requiresWebSearchTitle')}
                        >
                          {t('requiresWebSearch')}
                        </Badge>
                      )}
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
                  {source.description && (
                    <p className="text-xs text-muted-foreground leading-relaxed">{source.description}</p>
                  )}
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
                          {report.manifest?.limit != null && (
                            <span
                              className="ml-1.5 px-1.5 py-0.5 text-[10px] font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400 rounded"
                              title={t('sampledTitle')}
                            >
                              {t('sampled')} · {report.manifest.limit}
                            </span>
                          )}
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
                        <div
                          className="h-full bg-primary transition-all duration-300"
                          style={{ width: `${downloadPct}%` }}
                        />
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

                  <div className="flex items-center gap-2 mt-auto flex-wrap">
                    <div className="flex items-center gap-1.5 rounded-lg border bg-muted/20 px-2 py-1">
                      <Boxes className="w-3.5 h-3.5 text-muted-foreground" />
                      <input
                        type="number"
                        min={1}
                        value={sampleLimits[source.benchmark_id] ?? ''}
                        onChange={(e) =>
                          setSampleLimits((prev) => ({ ...prev, [source.benchmark_id]: e.target.value }))
                        }
                        disabled={running}
                        placeholder={t('sampleLimitPlaceholder')}
                        aria-label={t('sampleLimitTitle')}
                        className="w-20 bg-transparent text-sm outline-none placeholder:text-muted-foreground/60 disabled:opacity-50"
                        title={t('sampleLimitTitle')}
                      />
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onDownload(source.benchmark_id)}
                      disabled={running || source.is_downloaded}
                      className="flex-1 min-w-[96px]"
                    >
                      <DownloadCloud className="w-4 h-4" />
                      {source.is_downloaded ? t('downloaded') : downloadingThis ? t('downloading') : t('download')}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => onRun(source.benchmark_id, parseLimit(sampleLimits[source.benchmark_id] ?? ''))}
                      disabled={running}
                      className="flex-1 min-w-[96px]"
                    >
                      <Play className="w-4 h-4" />
                      {running ? t('running') : t('run')}
                    </Button>
                    {source.supports_memory_ab !== false && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setPendingMemoryAbBenchmark(source.benchmark_id);
                          setPendingMemoryAbLimit(parseLimit(sampleLimits[source.benchmark_id] ?? ''));
                        }}
                        disabled={running}
                        className="flex-1 min-w-[96px]"
                      >
                        <BrainCircuit className="w-4 h-4" />
                        {t('memoryAb')}
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setPendingLayerBenchmark(source.benchmark_id);
                        setPendingLayerLimit(parseLimit(sampleLimits[source.benchmark_id] ?? ''));
                      }}
                      disabled={running}
                      className="flex-1 min-w-[96px]"
                    >
                      <Layers className="w-4 h-4" />
                      {tLayers('button')}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      <Dialog
        open={pendingMemoryAbBenchmark != null}
        onOpenChange={(open) => !open && setPendingMemoryAbBenchmark(null)}
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
            <Button variant="outline" onClick={() => setPendingMemoryAbBenchmark(null)}>
              {tMemoryAb('confirmCancel')}
            </Button>
            <Button
              onClick={() => {
                const benchmarkId = pendingMemoryAbBenchmark;
                const limit = pendingMemoryAbLimit;
                setPendingMemoryAbBenchmark(null);
                setPendingMemoryAbLimit(undefined);
                if (benchmarkId) {
                  onMemoryAb(benchmarkId, limit);
                }
              }}
            >
              {tMemoryAb('confirmStart')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={pendingLayerBenchmark != null} onOpenChange={(open) => !open && setPendingLayerBenchmark(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              {tLayers('confirmTitle')}
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              {tLayers('confirmBody')}
              {selectedProfileName && (
                <span className="block mt-2 font-medium text-foreground">
                  {tLayers('confirmProfileHint')}: {selectedProfileName}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingLayerBenchmark(null)}>
              {tLayers('confirmCancel')}
            </Button>
            <Button
              onClick={() => {
                const benchmarkId = pendingLayerBenchmark;
                const limit = pendingLayerLimit;
                setPendingLayerBenchmark(null);
                setPendingLayerLimit(undefined);
                if (benchmarkId) {
                  onLayerEval(benchmarkId, limit);
                }
              }}
            >
              {tLayers('confirmStart')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

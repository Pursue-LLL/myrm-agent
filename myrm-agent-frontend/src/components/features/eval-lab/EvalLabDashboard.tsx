import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { LazyMonacoDiffEditor as DiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import { toast } from 'sonner';
import { Grid3X3, Play, Plus, RefreshCw, Save, XCircle } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import BenchmarkSources from './components/BenchmarkSources';
import CasesTab from './tabs/CasesTab';
import ReportTab from './tabs/ReportTab';
import MatrixTab from './tabs/MatrixTab';
import MemoryAbTab from './tabs/MemoryAbTab';
import HistoryTab from './tabs/HistoryTab';
import { formatMib } from './components/format';
import { useCasesEval, type EvalDataset, type EvalProfile } from './hooks/useCasesEval';
import { useMatrixEval } from './hooks/useMatrixEval';
import { useMemoryAbEval } from './hooks/useMemoryAbEval';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

export default function EvalLabDashboard() {
  const locale = useLocale();
  const t = useTranslations('evalLab');
  const [selectedDatasetId, setSelectedDatasetId] = useState('default');
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [profiles, setProfiles] = useState<EvalProfile[]>([]);
  const [selectedProfileIds, setSelectedProfileIds] = useState<string[]>([]);
  const [benchmarkMode, setBenchmarkMode] = useState(false);
  const [activeTab, setActiveTab] = useState('cases');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('new_dataset');
  const [globalReady, setGlobalReady] = useState(false);

  const casesEval = useCasesEval(selectedDatasetId);
  const matrixEval = useMatrixEval();
  const memoryAbEval = useMemoryAbEval();

  const isMatrixMode = selectedProfileIds.length >= 2;
  const anyBusy = casesEval.running || matrixEval.matrixRunning || memoryAbEval.memoryAbRunning;
  const loading = !(globalReady && casesEval.ready && matrixEval.ready && memoryAbEval.ready);

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

  useEffect(() => {
    Promise.all([fetchDatasets(), fetchProfiles()]).finally(() => setGlobalReady(true));
  }, [fetchDatasets, fetchProfiles]);

  const armNames = useMemo(
    () => ({
      memory_off: t('memoryAb.armNoMemory'),
      memory_on: t('memoryAb.armWithMemory'),
    }),
    [t],
  );

  const profileNames = useMemo(
    () => Object.fromEntries(profiles.map((p) => [p.agent_id, p.name || p.agent_id.slice(0, 8)])),
    [profiles],
  );

  const selectedProfileName = profiles.find((p) => p.agent_id === selectedProfileIds[0])?.name;

  const handleRun = async () => {
    if (anyBusy) {
      return;
    }
    if (casesEval.casesDraft !== casesEval.cases) {
      toast.error(t('saveFirst'));
      return;
    }
    if (isMatrixMode) {
      await matrixEval.startMatrix(selectedProfileIds, selectedDatasetId, benchmarkMode, () => setActiveTab('matrix'));
    } else {
      await casesEval.startRun(selectedProfileIds[0] || null, selectedDatasetId, benchmarkMode, () =>
        setActiveTab('report'),
      );
    }
  };

  const handleBenchmarkRun = (benchmarkId: string, limit?: number) => {
    if (anyBusy) {
      return;
    }
    casesEval.startBenchmark(benchmarkId, selectedProfileIds[0] || null, benchmarkMode, limit, () =>
      setActiveTab('report'),
    );
  };

  const handleBenchmarkDownload = (benchmarkId: string) => {
    if (anyBusy) {
      return;
    }
    casesEval.startDownload(benchmarkId, () => setActiveTab('sources'));
  };

  const handleMemoryAbRun = (benchmarkId: string, limit?: number) => {
    if (anyBusy) {
      return;
    }
    memoryAbEval.start(benchmarkId, selectedProfileIds[0] || null, limit, () => setActiveTab('memory-ab'));
  };

  const handleLayerEvalRun = (benchmarkId: string, limit?: number) => {
    if (anyBusy) {
      return;
    }
    matrixEval.startLayer(benchmarkId, selectedProfileIds[0] || null, limit, () => setActiveTab('matrix'));
  };

  const handleAbort = async () => {
    if (memoryAbEval.memoryAbRunning) {
      await memoryAbEval.abort();
    } else if (matrixEval.matrixRunning) {
      await matrixEval.abort();
    } else {
      await casesEval.abort();
    }
  };

  const handleSave = async () => {
    await casesEval.saveDraft(selectedDatasetId);
  };

  const handleCreateDataset = async () => {
    const name = newDatasetName.trim();
    if (!name) {
      return;
    }
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

  const handleHistoryLoad = async (filename: string) => {
    if (!filename || casesEval.loadingReport) {
      return;
    }
    const loaded = await casesEval.loadHistoryReport(filename);
    if (loaded) {
      setActiveTab('report');
    }
  };

  const handleViewDiff = (expected: string, actual: string) => {
    casesEval.openDiff(expected, actual);
    setActiveTab('diff');
  };

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">{t('loading')}</div>;
  }

  return (
    <div className="flex flex-col h-full bg-card rounded-xl border overflow-hidden">
      <div className="flex items-center justify-between p-4 border-b bg-muted/20">
        <div className="flex items-center gap-4">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-auto">
            <TabsList>
              <TabsTrigger value="cases">{t('tabs.cases')}</TabsTrigger>
              <TabsTrigger value="sources">{t('tabs.sources')}</TabsTrigger>
              <TabsTrigger value="report">{t('tabs.report')}</TabsTrigger>
              {(matrixEval.matrixReport || matrixEval.matrixRunning) && (
                <TabsTrigger value="matrix">{t('tabs.matrix')}</TabsTrigger>
              )}
              {(memoryAbEval.memoryAbReport || memoryAbEval.memoryAbRunning) && (
                <TabsTrigger value="memory-ab">{t('tabs.memoryAb')}</TabsTrigger>
              )}
              <TabsTrigger value="history">{t('tabs.history')}</TabsTrigger>
              {casesEval.diffView && <TabsTrigger value="diff">{t('tabs.diff')}</TabsTrigger>}
            </TabsList>
          </Tabs>
        </div>

        <div className="flex items-center gap-3">
          {casesEval.running && (
            <div className="flex items-center gap-2 text-sm">
              <RefreshCw className="w-4 h-4 animate-spin text-primary" />
              <span>
                {casesEval.evalStage === 'downloading'
                  ? `${t('wbBench.downloading')}: ${formatMib(casesEval.downloadProgress?.downloaded_bytes ?? 0)} / ${
                      casesEval.downloadProgress && casesEval.downloadProgress.total_bytes > 0
                        ? formatMib(casesEval.downloadProgress.total_bytes)
                        : '?'
                    }`
                  : `${t('progress')}: ${casesEval.progress.completed} / ${casesEval.progress.total}`}
              </span>
            </div>
          )}

          {activeTab === 'cases' && casesEval.casesDraft !== casesEval.cases && (
            <button
              onClick={handleSave}
              disabled={casesEval.saving}
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
              disabled={anyBusy}
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
              disabled={anyBusy}
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
                    if (anyBusy) {
                      return;
                    }
                    setSelectedProfileIds((prev) =>
                      isSelected ? prev.filter((id) => id !== p.agent_id) : [...prev, p.agent_id],
                    );
                  }}
                  disabled={anyBusy}
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
              disabled={anyBusy}
              className="rounded border-border text-primary focus:ring-primary"
            />
            {t('benchmarkMode')}
          </label>

          <button
            onClick={handleRun}
            disabled={anyBusy}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-green-600 text-white rounded-full hover:bg-green-700 disabled:opacity-50 disabled:bg-gray-400"
          >
            <Play className="w-4 h-4" />
            {anyBusy ? t('running') : isMatrixMode ? t('runMatrix') : t('run')}
          </button>

          {anyBusy && (
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
            <CasesTab casesDraft={casesEval.casesDraft} onDraftChange={casesEval.setCasesDraft} />
          </TabsContent>

          <TabsContent value="sources" className="h-full p-6 m-0">
            <BenchmarkSources
              running={anyBusy}
              history={casesEval.history}
              onRun={handleBenchmarkRun}
              onDownload={handleBenchmarkDownload}
              onMemoryAb={handleMemoryAbRun}
              onLayerEval={handleLayerEvalRun}
              refreshToken={casesEval.sourcesRefreshToken}
              downloadingBenchmarkId={casesEval.evalStage === 'downloading' ? casesEval.evalStageSubsetId : null}
              downloadProgress={casesEval.downloadProgress}
              selectedProfileName={selectedProfileName}
            />
          </TabsContent>

          <TabsContent value="report" className="h-full p-6 overflow-y-auto">
            <ReportTab
              running={casesEval.running}
              evalStage={casesEval.evalStage}
              progress={casesEval.progress}
              downloadProgress={casesEval.downloadProgress}
              report={casesEval.report}
              onViewDiff={handleViewDiff}
            />
          </TabsContent>

          <TabsContent value="matrix" className="h-full p-6 overflow-y-auto">
            <MatrixTab
              running={matrixEval.matrixRunning}
              progress={matrixEval.matrixProgress}
              report={matrixEval.matrixReport}
              history={matrixEval.matrixHistory}
              selectedTimestamp={matrixEval.selectedMatrixTs}
              profileNames={profileNames}
              onLoadReport={matrixEval.loadReport}
            />
          </TabsContent>

          <TabsContent value="memory-ab" className="h-full p-6 overflow-y-auto">
            <MemoryAbTab
              running={memoryAbEval.memoryAbRunning}
              progress={memoryAbEval.memoryAbProgress}
              report={memoryAbEval.memoryAbReport}
              history={memoryAbEval.memoryAbHistory}
              selectedTimestamp={memoryAbEval.selectedMemoryAbTs}
              armNames={armNames}
              onLoadReport={memoryAbEval.loadReport}
            />
          </TabsContent>

          <TabsContent value="history" className="h-full p-6 overflow-y-auto">
            <HistoryTab
              history={casesEval.history}
              loadingReport={casesEval.loadingReport}
              onLoadReport={handleHistoryLoad}
            />
          </TabsContent>

          {casesEval.diffView && (
            <TabsContent value="diff" className="h-full p-0 m-0">
              <DiffEditor
                height="100%"
                theme="vs-dark"
                original={casesEval.diffView.expected}
                modified={casesEval.diffView.actual}
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
            value={newDatasetName}
            onChange={(e) => setNewDatasetName(e.target.value)}
            placeholder={t('createDatasetPrompt')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleCreateDataset();
              }
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

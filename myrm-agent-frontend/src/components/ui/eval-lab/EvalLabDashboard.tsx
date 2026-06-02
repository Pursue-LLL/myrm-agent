import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { LazyMonacoEditor as Editor, LazyMonacoDiffEditor as DiffEditor } from '@/components/ui/lazy-monaco-editor';
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
  ChevronDown,
  ChevronRight,
  BookOpen,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

const ASSERTION_KEYS = [
  'expected_tools',
  'contains',
  'not_contains',
  'regex',
  'json_valid',
  'json_schema',
  'custom_python',
  'llm_judge',
  'llm_judge_threshold',
  'llm_judge_prompt',
  'sandbox',
] as const;

const ASSERTION_EXAMPLES: Record<string, string> = {
  expected_tools: '"expected_tools": ["web_search"]',
  contains: '"state_assertions": [{"type": "contains", "expected": "hello"}]',
  not_contains: '"state_assertions": [{"type": "not_contains", "expected": "error"}]',
  regex: '"state_assertions": [{"type": "regex", "expected": "\\\\d{4}-\\\\d{2}-\\\\d{2}"}]',
  json_valid: '"state_assertions": [{"type": "json_valid", "expected": ""}]',
  json_schema: '"state_assertions": [{"type": "json_schema", "expected": "{\\"required\\": [\\"name\\", \\"age\\"]}"}]',
  custom_python: '"state_assertions": [{"type": "custom_python", "expected": "len(output) < 2000"}]',
  llm_judge: '"semantic_assertions": [{"type": "llm_judge", "expected": "polite and professional"}]',
  llm_judge_threshold:
    '"semantic_assertions": [{"type": "llm_judge", "expected": "covers safety tips", "threshold": 0.7}]',
  llm_judge_prompt:
    '"semantic_assertions": [{"type": "llm_judge", "expected": "accuracy", "judge_prompt": "Judge if {output} meets {criteria}, reply PASS or FAIL: reason"}]',
  sandbox: '"sandbox_assertions": [{"type": "file_exists", "target": "output.txt"}]',
};

function CaseFormatReference({ t }: { t: (key: string) => string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b bg-muted/10 text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-4 py-2 w-full text-left text-muted-foreground hover:text-foreground transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <BookOpen className="w-3.5 h-3.5" />
        <span>{t('caseFormatRef')}</span>
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1.5 max-h-[200px] overflow-y-auto">
          <p className="text-muted-foreground mb-2">
            {t('caseFormatDesc')} <code className="bg-muted px-1 rounded">{`{"message": "your question"}`}</code>
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b">
                <th className="text-left py-1 pr-3 font-medium w-[140px]">{t('assertionType')}</th>
                <th className="text-left py-1 pr-3 font-medium w-[160px]">{t('assertionDesc')}</th>
                <th className="text-left py-1 font-medium">{t('assertionExample')}</th>
              </tr>
            </thead>
            <tbody>
              {ASSERTION_KEYS.map((key) => (
                <tr key={key} className="border-b border-border/30">
                  <td className="py-1 pr-3 text-primary font-mono">{key}</td>
                  <td className="py-1 pr-3 text-muted-foreground">{t(`assertions.${key}`)}</td>
                  <td className="py-1 font-mono text-foreground/80 break-all">{ASSERTION_EXAMPLES[key]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function EvalLabDashboard() {
  const t = useTranslations('evalLab');
  const [cases, setCases] = useState('');
  const [casesDraft, setCasesDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ total: 0, completed: 0 });
  const [report, setReport] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState('cases');
  const [diffView, setDiffView] = useState<{ expected: string; actual: string } | null>(null);
  const [profiles, setProfiles] = useState<any[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('default');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('new_dataset');
  const createInputRef = useRef<HTMLInputElement>(null);

  const fetchDatasets = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/datasets');
      const data = await res.json();
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
      const res = await fetch('/api/v1/system/profiles');
      const data = await res.json();
      if (Array.isArray(data.items)) {
        setProfiles(data.items);
      } else if (Array.isArray(data)) {
        setProfiles(data);
      }
    } catch (e) {
      console.error('Failed to fetch profiles', e);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/eval/status');
      const data = await res.json();
      setRunning(data.is_running);
      if (data.progress) {
        setProgress(data.progress);
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
      const data = await res.json();
      if (data.status === 'success' && data.summary) {
        setReport(data.summary);
      }
    } catch (e) {
      console.error('Failed to fetch latest report:', e);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchDatasets(), fetchStatus(), fetchReport(), fetchProfiles(), fetchHistory()]).finally(() =>
      setLoading(false),
    );
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

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setRunning(data.is_running);
          if (data.progress) {
            setProgress(data.progress);
          }

          if (!data.is_running) {
            eventSource?.close();
            fetchReport();
            fetchHistory();
          }
        } catch (e) {
          console.error('Failed to parse SSE data', e);
        }
      };

      eventSource.addEventListener('close', () => {
        eventSource?.close();
        setRunning(false);
        fetchReport();
        fetchHistory();
      });

      eventSource.onerror = () => {
        console.error('SSE Error');
        eventSource?.close();
        setRunning(false);
      };
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [running, fetchReport]);

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
    if (running) return;
    if (cases !== casesDraft) {
      toast.error(t('saveFirst'));
      return;
    }
    try {
      const res = await fetch('/api/v1/eval/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: selectedProfileId || null,
          dataset_id: selectedDatasetId,
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
  };

  const handleAbort = async () => {
    try {
      const res = await fetch('/api/v1/eval/abort', { method: 'POST' });
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

  const successRate = report && report.total > 0 ? Math.round((report.passed / report.total) * 100) : 0;

  return (
    <div className="flex flex-col h-full bg-card rounded-xl border overflow-hidden">
      <div className="flex items-center justify-between p-4 border-b bg-muted/20">
        <div className="flex items-center gap-4">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-auto">
            <TabsList>
              <TabsTrigger value="cases">{t('tabs.cases')}</TabsTrigger>
              <TabsTrigger value="report">{t('tabs.report')}</TabsTrigger>
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
                {t('progress')}: {progress.completed} / {progress.total}
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

          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            className="px-2 py-1.5 text-sm rounded-full border bg-background"
            disabled={running}
          >
            <option value="">{t('defaultConfig')}</option>
            {profiles.map((p) => (
              <option key={p.agent_id} value={p.agent_id}>
                {p.name || p.agent_id}
              </option>
            ))}
          </select>

          <button
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-green-600 text-white rounded-full hover:bg-green-700 disabled:opacity-50 disabled:bg-gray-400"
          >
            <Play className="w-4 h-4" />
            {running ? t('running') : t('run')}
          </button>

          {running && (
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

          <TabsContent value="report" className="h-full p-6 overflow-y-auto">
            {running ? (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                <RefreshCw className="w-8 h-8 animate-spin text-primary" />
                <p>
                  {t('report.evalRunning')} ({progress.completed} / {progress.total})
                </p>
                <div className="w-64 h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%` }}
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

                <div className="space-y-3">
                  <h3 className="text-lg font-medium">{t('report.executionDetails')}</h3>
                  <div className="border rounded-lg overflow-hidden">
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
                          report.cases.map((c: any, i: number) => (
                            <tr key={i} className="bg-card hover:bg-muted/20 transition-colors">
                              <td className="px-4 py-3">
                                {c.passed ? (
                                  <span className="flex items-center gap-1 text-green-600">
                                    <CheckCircle2 className="w-4 h-4" />
                                    {t('report.passed')}
                                  </span>
                                ) : (
                                  <span className="flex items-center gap-1 text-red-600">
                                    <XCircle className="w-4 h-4" />
                                    {t('report.failed')}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 max-w-xs truncate" title={c.case?.message}>
                                {c.case?.message || t('report.multiTurn')}
                              </td>
                              <td className="px-4 py-3">{c.usage?.total_tokens || 0}</td>
                              <td className="px-4 py-3">{c.time_secs ? c.time_secs.toFixed(2) : '-'}s</td>
                              <td className="px-4 py-3">
                                {c.details && (
                                  <button
                                    onClick={() => {
                                      const expected = {
                                        tools: c.case?.expected_tools || [],
                                        output: c.case?.state_assertions?.length ? c.case.state_assertions : undefined,
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
                                )}
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

          <TabsContent value="history" className="h-full p-6 overflow-y-auto">
            {history.length > 0 ? (
              <div className="space-y-6 max-w-4xl mx-auto">
                <div className="border rounded-lg p-4 bg-card h-[300px]">
                  <h3 className="text-sm font-medium mb-4 text-muted-foreground">{t('history.passRateTrend')}</h3>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={history} margin={{ top: 5, right: 20, bottom: 25, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis
                        dataKey={(d) => new Date(d.timestamp * 1000).toLocaleTimeString()}
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                      <RechartsTooltip
                        labelFormatter={(l) => `${t('history.time')}: ${l}`}
                        formatter={(val: number) => [`${Math.round(val)}%`, t('history.passRateLabel')]}
                      />
                      <Line
                        type="monotone"
                        dataKey={(d) => (d.passed / d.total) * 100}
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
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-muted/50 border-b">
                        <tr>
                          <th className="px-4 py-3 font-medium">{t('history.time')}</th>
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
                          .map((h: any, i: number) => {
                            const rate = h.total > 0 ? Math.round((h.passed / h.total) * 100) : 0;
                            return (
                              <tr key={i} className="bg-card hover:bg-muted/20 transition-colors">
                                <td className="px-4 py-3">{new Date(h.timestamp * 1000).toLocaleString()}</td>
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

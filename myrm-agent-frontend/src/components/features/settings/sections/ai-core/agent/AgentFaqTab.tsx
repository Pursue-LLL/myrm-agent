'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Pencil, Plus, Trash2, Upload, RefreshCw, BarChart3, HelpCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import { Textarea } from '@/components/primitives/textarea';
import { apiRequest } from '@/lib/api';
import { toast } from '@/hooks/shared/useToast';

interface FaqCorpus {
  id: string;
  agent_id: string;
  enabled: boolean;
  threshold: number;
  min_score_gap: number;
  entry_count: number;
}

interface FaqEntry {
  id: string;
  corpus_id: string;
  question: string;
  answer: string;
  tags: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

interface FaqStats {
  total: number;
  hits: number;
  misses: number;
  hit_rate: number;
}

interface UnmatchedItem {
  query: string;
  top_score: number;
  time: string;
}

interface AgentFaqTabProps {
  agentId: string | null;
}

export function AgentFaqTab({ agentId }: AgentFaqTabProps) {
  const t = useTranslations('agent.faq');
  const [corpus, setCorpus] = useState<FaqCorpus | null>(null);
  const [entries, setEntries] = useState<FaqEntry[]>([]);
  const [stats, setStats] = useState<FaqStats | null>(null);
  const [unmatched, setUnmatched] = useState<UnmatchedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingEntry, setEditingEntry] = useState<Partial<FaqEntry> | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [importJson, setImportJson] = useState('');
  const [showStats, setShowStats] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [localThreshold, setLocalThreshold] = useState<number>(0.85);
  const [localGap, setLocalGap] = useState<number>(0.15);

  const fetchData = useCallback(async () => {
    if (!agentId) {return;}
    setLoading(true);
    try {
      const [corpusRes, entriesRes] = await Promise.all([
        apiRequest<FaqCorpus>(`/faq/${agentId}/corpus`),
        apiRequest<FaqEntry[]>(`/faq/${agentId}/entries`),
      ]);
      setCorpus(corpusRes);
      setEntries(entriesRes);
      setLocalThreshold(corpusRes.threshold);
      setLocalGap(corpusRes.min_score_gap);
    } catch {
      /* corpus may not exist yet */
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleToggle = useCallback(
    async (enabled: boolean) => {
      if (!agentId) {return;}
      try {
        const updated = await apiRequest<FaqCorpus>(`/faq/${agentId}/corpus`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled }),
        });
        setCorpus(updated);
        toast({ title: t('saveSuccess') });
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [agentId, t],
  );

  const handleSettingsUpdate = useCallback(
    async (field: 'threshold' | 'min_score_gap', value: number) => {
      if (!agentId) {return;}
      try {
        const updated = await apiRequest<FaqCorpus>(`/faq/${agentId}/corpus`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [field]: value }),
        });
        setCorpus(updated);
        setLocalThreshold(updated.threshold);
        setLocalGap(updated.min_score_gap);
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [agentId, t],
  );

  const handleSaveEntry = useCallback(async () => {
    if (!agentId || !editingEntry?.question?.trim() || !editingEntry?.answer?.trim()) {return;}
    try {
      if (editingEntry.id) {
        await apiRequest(`/faq/entries/${editingEntry.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: editingEntry.question,
            answer: editingEntry.answer,
            tags: editingEntry.tags || '',
          }),
        });
        toast({ title: t('entryUpdated') });
      } else {
        await apiRequest(`/faq/${agentId}/entries`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: editingEntry.question,
            answer: editingEntry.answer,
            tags: editingEntry.tags || '',
          }),
        });
        toast({ title: t('entryCreated') });
      }
      setEditingEntry(null);
      await fetchData();
    } catch {
      toast({ title: t('saveFailed'), variant: 'destructive' });
    }
  }, [agentId, editingEntry, fetchData, t]);

  const handleDeleteEntry = useCallback(
    async (entryId: string) => {
      try {
        await apiRequest(`/faq/entries/${entryId}`, { method: 'DELETE' });
        toast({ title: t('entryDeleted') });
        await fetchData();
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      }
    },
    [fetchData, t],
  );

  const handleImport = useCallback(async () => {
    if (!agentId || !importJson.trim()) {return;}
    try {
      const parsed = JSON.parse(importJson);
      const items = Array.isArray(parsed) ? parsed : [parsed];
      const res = await apiRequest<{ imported: number }>(`/faq/${agentId}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      });
      toast({ title: t('importSuccess', { count: res.imported }) });
      setImportJson('');
      setShowImport(false);
      await fetchData();
    } catch {
      toast({ title: t('importFailed'), variant: 'destructive' });
    }
  }, [agentId, importJson, fetchData, t]);

  const handleRebuild = useCallback(async () => {
    if (!agentId) {return;}
    setRebuilding(true);
    try {
      const res = await apiRequest<{ indexed: number }>(`/faq/${agentId}/rebuild-index`, { method: 'POST' });
      toast({ title: t('rebuildSuccess', { count: res.indexed }) });
    } catch {
      toast({ title: t('rebuildFailed'), variant: 'destructive' });
    } finally {
      setRebuilding(false);
    }
  }, [agentId, t]);

  const handleLoadStats = useCallback(async () => {
    if (!agentId) {return;}
    setShowStats(true);
    try {
      const [statsRes, unmatchedRes] = await Promise.all([
        apiRequest<FaqStats>(`/faq/${agentId}/stats`),
        apiRequest<UnmatchedItem[]>(`/faq/${agentId}/unmatched?limit=20`),
      ]);
      setStats(statsRes);
      setUnmatched(unmatchedRes);
    } catch {
      /* no stats yet */
    }
  }, [agentId]);

  if (!agentId) {return null;}

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-border/60 bg-card/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold">{t('title')}</h3>
            <p className="text-sm text-muted-foreground mt-1">{t('desc')}</p>
          </div>
          <Switch checked={corpus?.enabled ?? false} onCheckedChange={handleToggle} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
          <div className="space-y-2">
            <Label className="text-sm">{t('threshold')}</Label>
            <Input
              type="number"
              min={0.75}
              max={1.0}
              step={0.01}
              value={localThreshold}
              onChange={(e) => setLocalThreshold(Number(e.target.value))}
              onBlur={() => void handleSettingsUpdate('threshold', localThreshold)}
              className="max-w-[140px]"
            />
            <p className="text-xs text-muted-foreground">{t('thresholdDesc')}</p>
          </div>
          <div className="space-y-2">
            <Label className="text-sm">{t('minScoreGap')}</Label>
            <Input
              type="number"
              min={0}
              max={0.5}
              step={0.01}
              value={localGap}
              onChange={(e) => setLocalGap(Number(e.target.value))}
              onBlur={() => void handleSettingsUpdate('min_score_gap', localGap)}
              className="max-w-[140px]"
            />
            <p className="text-xs text-muted-foreground">{t('minScoreGapDesc')}</p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border/60 bg-card/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">
            {t('title')} ({entries.length})
          </h3>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowImport(!showImport)}>
              <Upload className="w-3.5 h-3.5 mr-1" />
              {t('import')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleRebuild}
              disabled={rebuilding || entries.length === 0}
            >
              <RefreshCw className={cn('w-3.5 h-3.5 mr-1', rebuilding && 'animate-spin')} />
              {t('rebuildIndex')}
            </Button>
            <Button size="sm" variant="outline" onClick={handleLoadStats}>
              <BarChart3 className="w-3.5 h-3.5 mr-1" />
              {t('stats')}
            </Button>
            <Button
              size="sm"
              onClick={() => setEditingEntry({ question: '', answer: '', tags: '' })}
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              {t('addEntry')}
            </Button>
          </div>
        </div>

        {showImport && (
          <div className="mb-4 p-4 rounded-xl border border-border/50 bg-muted/30 space-y-3">
            <p className="text-sm text-muted-foreground">{t('importDesc')}</p>
            <Textarea
              value={importJson}
              onChange={(e) => setImportJson(e.target.value)}
              placeholder='[{"question": "...", "answer": "..."}]'
              className="min-h-[80px] font-mono text-xs"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleImport} disabled={!importJson.trim()}>
                {t('importBtn')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowImport(false)}>
                {t('cancel')}
              </Button>
            </div>
          </div>
        )}

        {editingEntry && (
          <div className="mb-4 p-4 rounded-xl border border-primary/20 bg-primary/5 space-y-3">
            <h4 className="text-sm font-medium">
              {editingEntry.id ? t('editEntry') : t('addEntry')}
            </h4>
            <div className="space-y-2">
              <Label className="text-xs">{t('question')}</Label>
              <Input
                value={editingEntry.question || ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, question: e.target.value })}
                placeholder={t('questionPlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs">{t('answer')}</Label>
              <Textarea
                value={editingEntry.answer || ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, answer: e.target.value })}
                placeholder={t('answerPlaceholder')}
                className="min-h-[80px]"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs">{t('tags')}</Label>
              <Input
                value={editingEntry.tags || ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, tags: e.target.value })}
                placeholder={t('tagsPlaceholder')}
              />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveEntry}>
                {t('save')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditingEntry(null)}>
                {t('cancel')}
              </Button>
            </div>
          </div>
        )}

        {entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <HelpCircle className="w-10 h-10 text-muted-foreground/50 mb-3" />
            <h4 className="text-sm font-medium text-muted-foreground">{t('emptyTitle')}</h4>
            <p className="text-xs text-muted-foreground/70 mt-1">{t('emptyDesc')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {entries.map((entry) => (
              <div
                key={entry.id}
                className="flex items-start gap-3 p-3 rounded-xl border border-border/50 hover:border-border transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{entry.question}</p>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{entry.answer}</p>
                  {entry.tags && (
                    <div className="flex gap-1 mt-1.5">
                      {entry.tags.split(',').map((tag) => (
                        <span
                          key={tag.trim()}
                          className="px-1.5 py-0.5 rounded text-[10px] bg-muted text-muted-foreground"
                        >
                          {tag.trim()}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => setEditingEntry(entry)}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 text-destructive"
                    onClick={() => void handleDeleteEntry(entry.id)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showStats && stats && (
        <div className="rounded-2xl border border-border/60 bg-card/50 p-6 space-y-4">
          <h3 className="text-lg font-semibold">{t('stats')}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="text-center p-3 rounded-xl bg-muted/30">
              <p className="text-2xl font-bold">{stats.total}</p>
              <p className="text-xs text-muted-foreground">{t('statsTotal')}</p>
            </div>
            <div className="text-center p-3 rounded-xl bg-emerald-500/10">
              <p className="text-2xl font-bold text-emerald-600">{stats.hits}</p>
              <p className="text-xs text-muted-foreground">{t('statsHits')}</p>
            </div>
            <div className="text-center p-3 rounded-xl bg-amber-500/10">
              <p className="text-2xl font-bold text-amber-600">{stats.misses}</p>
              <p className="text-xs text-muted-foreground">{t('statsMisses')}</p>
            </div>
            <div className="text-center p-3 rounded-xl bg-primary/10">
              <p className="text-2xl font-bold text-primary">{(stats.hit_rate * 100).toFixed(1)}%</p>
              <p className="text-xs text-muted-foreground">{t('statsHitRate')}</p>
            </div>
          </div>

          {unmatched.length > 0 && (
            <div className="mt-4">
              <h4 className="text-sm font-medium mb-2">{t('unmatched')}</h4>
              <p className="text-xs text-muted-foreground mb-3">{t('unmatchedDesc')}</p>
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                {unmatched.map((item, i) => (
                  <div
                    key={`${item.time}-${i}`}
                    className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/30 text-sm"
                  >
                    <span className="truncate flex-1">{item.query}</span>
                    <span className="text-xs text-muted-foreground ml-2 shrink-0">
                      {item.top_score.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

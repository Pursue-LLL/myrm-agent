'use client';

import { useState, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives/tabs';
import { IconBook, IconGlow, IconWrench, IconDatabase, IconExplore } from '@/components/features/icons/PremiumIcons';
import { Textarea } from '@/components/primitives/textarea';
import { apiRequest } from '@/lib/api';
import { isTauri } from '@/lib/utils/clipboardUtils';
import { wikiService, type ObsidianImportResultResponse } from '@/services/wikiService';
import { WikiConceptsList } from './WikiConceptsList';
import { WikiPendingEdits } from './WikiPendingEdits';
import { WikiQueuePanel } from './WikiQueuePanel';

interface WikiStats {
  total_concepts: number;
  total_articles: number;
  total_raw_files: number;
  wiki_path: string;
  vault_ready: boolean;
  legacy_migrated: boolean;
}

interface WikiQueryResponse {
  question: string;
  answer: string;
  related_articles: string[];
}

export function WikiSection() {
  const t = useTranslations('settings.wiki');
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [relatedArticles, setRelatedArticles] = useState<string[]>([]);
  const [stats, setStats] = useState<WikiStats | null>(null);
  const [isQuerying, setIsQuerying] = useState(false);
  const [isCompiling, setIsCompiling] = useState(false);
  const [isMaintaining, setIsMaintaining] = useState(false);
  const [isLoadingStats, setIsLoadingStats] = useState(false);
  const [purpose, setPurpose] = useState('');
  const [purposeDraft, setPurposeDraft] = useState('');
  const [isLoadingPurpose, setIsLoadingPurpose] = useState(false);
  const [isSavingPurpose, setIsSavingPurpose] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isImportingObsidian, setIsImportingObsidian] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const zipInputRef = useRef<HTMLInputElement>(null);
  const obsidianZipRef = useRef<HTMLInputElement>(null);

  const isTauriEnv = isTauri();

  const handleImportFolder = async () => {
    if (!isTauriEnv) return;
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false, title: t('import.selectFolder') });
      if (!selected) return;

      setIsImporting(true);
      const result = await wikiService.importFolder(selected as string);
      if (result.success) {
        toast.success(result.message);
        setActiveTab('queue');
        await loadStats();
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Folder import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
    }
  };

  const handleImportZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsImporting(true);
    try {
      const result = await wikiService.importZip(file);
      if (result.success) {
        toast.success(result.message);
        setActiveTab('queue');
        await loadStats();
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('ZIP import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      if (zipInputRef.current) zipInputRef.current.value = '';
    }
  };

  const showObsidianResult = (result: ObsidianImportResultResponse) => {
    toast.success(
      t('import.obsidianResult', {
        processed: result.files_processed,
        tags: result.tags_extracted,
        images: result.images_copied,
        skipped: result.files_skipped,
      }),
    );
  };

  const handleImportObsidianFolder = async () => {
    if (!isTauriEnv) return;
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false, title: t('import.selectObsidianVault') });
      if (!selected) return;

      setIsImportingObsidian(true);
      const result = await wikiService.importObsidianFolder(selected as string);
      if (result.success) {
        showObsidianResult(result);
        setActiveTab('queue');
        await loadStats();
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Obsidian folder import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImportingObsidian(false);
    }
  };

  const handleImportObsidianZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsImportingObsidian(true);
    try {
      const result = await wikiService.importObsidianZip(file);
      if (result.success) {
        showObsidianResult(result);
        setActiveTab('queue');
        await loadStats();
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Obsidian ZIP import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImportingObsidian(false);
      if (obsidianZipRef.current) obsidianZipRef.current.value = '';
    }
  };

  useEffect(() => {
    void loadPurpose();
    void loadStats();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadPurpose = async () => {
    setIsLoadingPurpose(true);
    try {
      const data = await apiRequest<{ purpose: string }>('/wiki/purpose');
      setPurpose(data.purpose);
      setPurposeDraft(data.purpose);
    } catch (error) {
      console.error('Failed to load purpose:', error);
    } finally {
      setIsLoadingPurpose(false);
    }
  };

  const handleSavePurpose = async () => {
    setIsSavingPurpose(true);
    try {
      await apiRequest('/wiki/purpose', {
        method: 'PUT',
        body: JSON.stringify({ purpose: purposeDraft }),
      });
      setPurpose(purposeDraft);
      toast.success(t('success.purposeSaved'));
    } catch (error) {
      console.error('Failed to save purpose:', error);
      toast.error(t('errors.purposeSaveFailed'));
    } finally {
      setIsSavingPurpose(false);
    }
  };

  const loadStats = async () => {
    setIsLoadingStats(true);
    try {
      const data = await apiRequest<WikiStats>('/wiki/stats');
      setStats(data);
    } catch (error) {
      console.error('Failed to load Wiki stats:', error);
      toast.error(t('errors.loadStatsFailed'));
    } finally {
      setIsLoadingStats(false);
    }
  };

  const handleQuery = async () => {
    if (!query.trim()) {
      toast.error(t('errors.emptyQuery'));
      return;
    }

    setIsQuerying(true);
    setAnswer('');
    setRelatedArticles([]);

    try {
      const data = await apiRequest<WikiQueryResponse>('/wiki/query', {
        method: 'POST',
        body: JSON.stringify({ question: query }),
      });

      setAnswer(data.answer);
      setRelatedArticles(data.related_articles || []);
      toast.success(t('success.queryComplete'));
    } catch (error) {
      console.error('Query failed:', error);
      toast.error(t('errors.queryFailed'));
    } finally {
      setIsQuerying(false);
    }
  };

  const handleCompile = async () => {
    setIsCompiling(true);
    try {
      await apiRequest('/wiki/compile', { method: 'POST' });
      toast.success(t('success.compileComplete'));
      await loadStats();
    } catch (error) {
      console.error('Compile failed:', error);
      toast.error(t('errors.compileFailed'));
    } finally {
      setIsCompiling(false);
    }
  };

  const handleMaintain = async () => {
    setIsMaintaining(true);
    try {
      await apiRequest('/wiki/maintain', { method: 'POST' });
      toast.success(t('success.maintainComplete'));
      await loadStats();
    } catch (error) {
      console.error('Maintain failed:', error);
      toast.error(t('errors.maintainFailed'));
    } finally {
      setIsMaintaining(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold mb-2">{t('title')}</h2>
        <p className="text-muted-foreground">{t('description')}</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col flex-1 min-h-0 space-y-6">
        <TabsList>
          <TabsTrigger value="overview">{t('tabs.overview')}</TabsTrigger>
          <TabsTrigger value="concepts">{t('tabs.concepts')}</TabsTrigger>
          <TabsTrigger value="pendingEdits">{t('tabs.pendingEdits')}</TabsTrigger>
          <TabsTrigger value="queue">{t('tabs.queue')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Purpose / Direction */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconExplore className="w-5 h-5" />
                {t('purpose.title')}
              </CardTitle>
              <CardDescription>{t('purpose.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {isLoadingPurpose ? (
                <div className="text-center py-4 text-muted-foreground">{t('loading')}</div>
              ) : (
                <>
                  <Textarea
                    placeholder={t('purpose.placeholder')}
                    value={purposeDraft}
                    onChange={(e) => setPurposeDraft(e.target.value)}
                    rows={3}
                    className="resize-none"
                  />
                  <div className="flex justify-end gap-2">
                    {purposeDraft !== purpose && (
                      <Button variant="ghost" size="sm" onClick={() => setPurposeDraft(purpose)}>
                        {t('purpose.reset')}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={handleSavePurpose}
                      disabled={isSavingPurpose || purposeDraft === purpose}
                    >
                      {isSavingPurpose ? t('purpose.saving') : t('purpose.save')}
                    </Button>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Wiki Stats */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconDatabase className="w-5 h-5" />
                {t('stats.title')}
              </CardTitle>
              <CardDescription>{t('stats.description')}</CardDescription>
            </CardHeader>
            <CardContent>
              {!stats && !isLoadingStats && (
                <Button onClick={loadStats} variant="outline">
                  {t('actions.loadStats')}
                </Button>
              )}

              {isLoadingStats && <div className="text-center py-4 text-muted-foreground">{t('loading')}</div>}

              {stats && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span
                      className={
                        stats.vault_ready
                          ? 'inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-emerald-600 dark:text-emerald-400'
                          : 'inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400'
                      }
                    >
                      {stats.vault_ready ? t('stats.vaultReady') : t('stats.vaultNotReady')}
                    </span>
                    {stats.legacy_migrated ? (
                      <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-emerald-600 dark:text-emerald-400">
                        {t('stats.legacyMigrated')}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                        {t('stats.legacyPending')}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-4 bg-muted rounded-lg">
                    <div className="text-3xl font-bold">{stats.total_concepts}</div>
                    <div className="text-sm text-muted-foreground">{t('stats.concepts')}</div>
                  </div>
                  <div className="text-center p-4 bg-muted rounded-lg">
                    <div className="text-3xl font-bold">{stats.total_articles}</div>
                    <div className="text-sm text-muted-foreground">{t('stats.articles')}</div>
                  </div>
                  <div className="text-center p-4 bg-muted rounded-lg">
                    <div className="text-3xl font-bold">{stats.total_raw_files}</div>
                    <div className="text-sm text-muted-foreground">{t('stats.rawFiles')}</div>
                  </div>
                  <div className="col-span-2 md:col-span-1 flex items-center justify-center">
                    <Button onClick={loadStats} variant="ghost" size="sm">
                      {t('actions.refresh')}
                    </Button>
                  </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Wiki Query */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconBook className="w-5 h-5" />
                {t('query.title')}
              </CardTitle>
              <CardDescription>{t('query.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder={t('query.placeholder')}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                />
                <Button onClick={handleQuery} disabled={isQuerying || !query.trim()}>
                  {isQuerying ? t('querying') : t('actions.query')}
                </Button>
              </div>

              {answer && (
                <div className="space-y-2">
                  <div className="text-sm font-medium">{t('query.answer')}</div>
                  <div className="p-4 bg-muted rounded-lg whitespace-pre-wrap">{answer}</div>

                  {relatedArticles.length > 0 && (
                    <div className="mt-4">
                      <div className="text-sm font-medium mb-2">{t('query.relatedArticles')}</div>
                      <div className="flex flex-wrap gap-2">
                        {relatedArticles.map((article, idx) => (
                          <span key={idx} className="px-2 py-1 bg-primary/10 text-primary rounded text-sm">
                            {article}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Wiki Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconWrench className="w-5 h-5" />
                {t('actions.title')}
              </CardTitle>
              <CardDescription>{t('actions.description')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col sm:flex-row gap-4">
              <Button onClick={handleCompile} disabled={isCompiling} className="flex-1">
                <IconGlow className="w-4 h-4 mr-2" />
                {isCompiling ? t('compiling') : t('actions.compile')}
              </Button>
              <Button onClick={handleMaintain} disabled={isMaintaining} variant="outline" className="flex-1">
                <IconWrench className="w-4 h-4 mr-2" />
                {isMaintaining ? t('maintaining') : t('actions.maintain')}
              </Button>
            </CardContent>
          </Card>

          {/* Batch Import */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconDatabase className="w-5 h-5" />
                {t('import.title')}
              </CardTitle>
              <CardDescription>{t('import.description')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col sm:flex-row gap-4">
              {isTauriEnv && (
                <Button onClick={handleImportFolder} disabled={isImporting} variant="outline" className="flex-1">
                  <IconExplore className="w-4 h-4 mr-2" />
                  {isImporting ? t('import.importing') : t('import.folder')}
                </Button>
              )}
              <Button
                onClick={() => zipInputRef.current?.click()}
                disabled={isImporting}
                variant="outline"
                className="flex-1"
              >
                <IconBook className="w-4 h-4 mr-2" />
                {isImporting ? t('import.importing') : t('import.zip')}
              </Button>
              <input
                ref={zipInputRef}
                type="file"
                accept=".zip"
                onChange={handleImportZip}
                className="hidden"
              />
            </CardContent>
          </Card>

          {/* Obsidian Vault Import */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconBook className="w-5 h-5" />
                {t('import.obsidianTitle')}
              </CardTitle>
              <CardDescription>{t('import.obsidianDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col sm:flex-row gap-4">
              {isTauriEnv && (
                <Button
                  onClick={handleImportObsidianFolder}
                  disabled={isImportingObsidian}
                  variant="outline"
                  className="flex-1"
                >
                  <IconExplore className="w-4 h-4 mr-2" />
                  {isImportingObsidian ? t('import.importing') : t('import.obsidianFolder')}
                </Button>
              )}
              <Button
                onClick={() => obsidianZipRef.current?.click()}
                disabled={isImportingObsidian}
                variant="outline"
                className="flex-1"
              >
                <IconDatabase className="w-4 h-4 mr-2" />
                {isImportingObsidian ? t('import.importing') : t('import.obsidianZip')}
              </Button>
              <input
                ref={obsidianZipRef}
                type="file"
                accept=".zip"
                onChange={handleImportObsidianZip}
                className="hidden"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="concepts" className="space-y-6 flex flex-col flex-1 min-h-0">
          <WikiConceptsList />
        </TabsContent>

        <TabsContent value="pendingEdits" className="space-y-6">
          <WikiPendingEdits />
        </TabsContent>

        <TabsContent value="queue" className="space-y-6">
          <WikiQueuePanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

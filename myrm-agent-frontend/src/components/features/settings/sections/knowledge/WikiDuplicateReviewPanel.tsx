'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { IconCopy, IconCheck, IconLoader, IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import {
  wikiService,
  WikiDedupDispositionAction,
  WikiDedupGroup,
  WikiDedupMemberSnippet,
  WikiDedupTier,
  WikiDedupVaultHygiene,
} from '@/services/wikiService';
import { ApiError } from '@/lib/api';
import { WikiScopeChip } from './WikiScopeChip';
import {
  DEDUP_POLL_INTERVAL_MS,
  DEDUP_POLL_MAX_ATTEMPTS,
  isDedupScanTerminalPhase,
  shouldResumeDedupPoll,
  shouldNotifyDedupScanFailedOnMount,
} from './wikiDedupPoll';

interface WikiDuplicateReviewPanelProps {
  agentScopeId?: string | null;
  scopeLabel: string;
  onVaultMutated?: () => void;
}

type TierFilter = 'all' | WikiDedupTier;

function formatBytes(sizeBytes: number): string {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMtimeNs(mtimeNs: number, locale: string): string {
  if (mtimeNs <= 0) {
    return '—';
  }
  const modifiedMs = Math.floor(mtimeNs / 1_000_000);
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(modifiedMs);
}

function tierBadgeClass(tier: WikiDedupTier): string {
  if (tier === 'exact') {
    return 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30';
  }
  if (tier === 'normalized') {
    return 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30';
  }
  return 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/30';
}

export function WikiDuplicateReviewPanel({
  agentScopeId,
  scopeLabel,
  onVaultMutated,
}: WikiDuplicateReviewPanelProps) {
  const t = useTranslations('settings.wiki.duplicateReview');
  const locale = useLocale();
  const [groups, setGroups] = useState<WikiDedupGroup[]>([]);
  const [tierFilter, setTierFilter] = useState<TierFilter>('all');
  const [isLoading, setIsLoading] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [activeGroupId, setActiveGroupId] = useState<number | null>(null);
  const [reasonDraft, setReasonDraft] = useState('');
  const [pendingAction, setPendingAction] = useState<WikiDedupDispositionAction | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [vaultHygiene, setVaultHygiene] = useState<WikiDedupVaultHygiene>({ trashed: [], excluded: [] });
  const [isHygieneLoading, setIsHygieneLoading] = useState(false);
  const [restoringPath, setRestoringPath] = useState<string | null>(null);
  const [expandedSnippetGroupId, setExpandedSnippetGroupId] = useState<number | null>(null);
  const [snippetCache, setSnippetCache] = useState<Record<number, WikiDedupMemberSnippet[]>>({});
  const [snippetLoadingGroupId, setSnippetLoadingGroupId] = useState<number | null>(null);

  const loadVaultHygiene = useCallback(async () => {
    setIsHygieneLoading(true);
    try {
      const snapshot = await wikiService.getWikiDedupVaultHygiene(agentScopeId);
      setVaultHygiene(snapshot);
    } catch (error) {
      console.error('Failed to load vault hygiene:', error);
      toast.error(t('vaultHygiene.errors.loadFailed'));
    } finally {
      setIsHygieneLoading(false);
    }
  }, [agentScopeId, t]);

  const loadGroups = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await wikiService.getWikiDuplicateGroups(agentScopeId);
      setGroups(result.filter((group) => group.status === 'open' || group.status === 'deferred'));
      setSnippetCache({});
      setExpandedSnippetGroupId(null);
    } catch (error) {
      console.error('Failed to load duplicate groups:', error);
      toast.error(t('errors.loadFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [agentScopeId, t]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadGroups(), loadVaultHygiene()]);
  }, [loadGroups, loadVaultHygiene]);

  useEffect(() => {
    setGroups([]);
    setActiveGroupId(null);
    setReasonDraft('');
    setPendingAction(null);
    setVaultHygiene({ trashed: [], excluded: [] });
    setSnippetCache({});
    setExpandedSnippetGroupId(null);
    setSnippetLoadingGroupId(null);
    void refreshAll();
  }, [refreshAll]);

  const filteredGroups = useMemo(() => {
    if (tierFilter === 'all') {
      return groups;
    }
    return groups.filter((group) => group.tier === tierFilter);
  }, [groups, tierFilter]);

  const openCount = groups.filter((group) => group.status === 'open').length;
  const blockingCount = groups.filter(
    (group) => group.status === 'open' && (group.tier === 'exact' || group.tier === 'normalized'),
  ).length;

  const pollScanUntilDone = useCallback(async () => {
    for (let attempt = 0; attempt < DEDUP_POLL_MAX_ATTEMPTS; attempt += 1) {
      const progress = await wikiService.getWikiDedupProgress(agentScopeId);
      if (isDedupScanTerminalPhase(progress.phase)) {
        if (progress.phase === 'done') {
          toast.success(
            t('scan.complete', {
              open: progress.groups_found,
              scanned: progress.files_scanned,
            }),
          );
          await loadGroups();
          await loadVaultHygiene();
          onVaultMutated?.();
        } else if (progress.phase === 'failed') {
          toast.error(t('errors.scanFailed'));
        }
        return;
      }
      await new Promise((resolve) => {
        window.setTimeout(resolve, DEDUP_POLL_INTERVAL_MS);
      });
    }
    toast.message(t('scan.stillRunning'));
  }, [agentScopeId, loadGroups, loadVaultHygiene, onVaultMutated, t]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const progress = await wikiService.getWikiDedupProgress(agentScopeId);
        if (cancelled) {
          return;
        }
        if (shouldNotifyDedupScanFailedOnMount(progress.phase)) {
          toast.error(t('errors.scanFailed'));
          return;
        }
        if (!shouldResumeDedupPoll(progress.phase)) {
          return;
        }
        setIsScanning(true);
        await pollScanUntilDone();
        if (!cancelled) {
          setIsScanning(false);
        }
      } catch (error) {
        console.error('Failed to resume dedup scan progress:', error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentScopeId, pollScanUntilDone]);

  const handleScan = async () => {
    setIsScanning(true);
    try {
      const result = await wikiService.scanWikiDuplicates(agentScopeId, true);
      if (result.skipped) {
        if (result.skipped_reason === 'scan_in_progress') {
          toast.message(t('scan.alreadyRunning'));
          await pollScanUntilDone();
          return;
        }
        toast.message(t('scan.skipped'));
        return;
      }
      if (result.accepted) {
        toast.message(t('scan.accepted'));
        await pollScanUntilDone();
      }
    } catch (error) {
      console.error('Dedup scan failed:', error);
      if (error instanceof ApiError && error.code === 409) {
        toast.error(t('errors.scanCompileBusy'));
        return;
      }
      toast.error(t('errors.scanFailed'));
    } finally {
      setIsScanning(false);
    }
  };

  const startDisposition = (groupId: number, action: WikiDedupDispositionAction) => {
    setActiveGroupId(groupId);
    setPendingAction(action);
    setReasonDraft('');
  };

  const cancelDisposition = () => {
    setActiveGroupId(null);
    setPendingAction(null);
    setReasonDraft('');
  };

  const handleApplyDisposition = async () => {
    if (activeGroupId === null || pendingAction === null) {
      return;
    }
    const needsReason = pendingAction === 'trash' || pendingAction === 'exclude';
    if (needsReason && !reasonDraft.trim()) {
      toast.error(t('errors.reasonRequired'));
      return;
    }
    setIsApplying(true);
    try {
      const result = await wikiService.applyWikiDuplicateDisposition(
        activeGroupId,
        pendingAction,
        reasonDraft.trim(),
        agentScopeId,
      );
      toast.success(
        t('success.disposition', {
          action: t(`actions.${pendingAction}`),
          count: result.affected_paths.length,
        }),
      );
      cancelDisposition();
      await refreshAll();
      onVaultMutated?.();
    } catch (error) {
      console.error('Disposition failed:', error);
      toast.error(t('errors.dispositionFailed'));
    } finally {
      setIsApplying(false);
    }
  };

  const handleRestoreTrashed = async (relativePath: string) => {
    setRestoringPath(relativePath);
    try {
      await wikiService.restoreWikiDedupTrashedRaw(relativePath, agentScopeId);
      toast.success(t('vaultHygiene.success.restoredTrash'));
      await refreshAll();
      onVaultMutated?.();
    } catch (error) {
      console.error('Failed to restore trashed raw file:', error);
      toast.error(t('vaultHygiene.errors.restoreFailed'));
    } finally {
      setRestoringPath(null);
    }
  };

  const handleUndoExcluded = async (relativePath: string) => {
    setRestoringPath(relativePath);
    try {
      await wikiService.undoWikiDedupExcludedRaw(relativePath, agentScopeId);
      toast.success(t('vaultHygiene.success.restoredExclude'));
      await refreshAll();
      onVaultMutated?.();
    } catch (error) {
      console.error('Failed to undo excluded raw file:', error);
      toast.error(t('vaultHygiene.errors.restoreFailed'));
    } finally {
      setRestoringPath(null);
    }
  };

  const handleToggleSnippets = async (groupId: number) => {
    if (expandedSnippetGroupId === groupId) {
      setExpandedSnippetGroupId(null);
      return;
    }
    setExpandedSnippetGroupId(groupId);
    if (snippetCache[groupId]) {
      return;
    }
    setSnippetLoadingGroupId(groupId);
    try {
      const snippets = await wikiService.getWikiDedupGroupSnippets(groupId, agentScopeId);
      setSnippetCache((current) => ({ ...current, [groupId]: snippets }));
    } catch (error) {
      console.error('Failed to load duplicate snippets:', error);
      toast.error(t('errors.snippetsFailed'));
      setExpandedSnippetGroupId(null);
    } finally {
      setSnippetLoadingGroupId(null);
    }
  };

  const filterOptions: Array<{ id: TierFilter; label: string }> = [
    { id: 'all', label: t('filters.all') },
    { id: 'exact', label: t('filters.exact') },
    { id: 'normalized', label: t('filters.normalized') },
    { id: 'near', label: t('filters.near') },
  ];

  return (
    <Card data-testid="wiki-dedup-panel">
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <IconCopy className="w-5 h-5" />
            {t('title')}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <WikiScopeChip scopeLabel={scopeLabel} />
            {openCount > 0 && (
              <Badge variant="secondary" className="bg-amber-500/10 text-amber-600 hover:bg-amber-500/20">
                {openCount} {t('status.open')}
              </Badge>
            )}
            {blockingCount > 0 && (
              <Badge variant="secondary" className="bg-rose-500/10 text-rose-600 hover:bg-rose-500/20">
                {blockingCount} {t('status.blocksCompile')}
              </Badge>
            )}
          </div>
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void handleScan()} disabled={isScanning} data-testid="wiki-dedup-scan-btn">
            {isScanning ? (
              <>
                <IconLoader className="w-4 h-4 mr-1.5 animate-spin" />
                {t('scan.running')}
              </>
            ) : (
              t('scan.run')
            )}
          </Button>
          <Button size="sm" variant="outline" onClick={() => void refreshAll()} disabled={isLoading || isHygieneLoading}>
            {t('actions.refresh')}
          </Button>
        </div>

        {groups.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {filterOptions.map((option) => (
              <Button
                key={option.id}
                size="sm"
                variant={tierFilter === option.id ? 'default' : 'outline'}
                onClick={() => setTierFilter(option.id)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        )}

        {blockingCount > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/5 p-3 text-sm text-rose-700 dark:text-rose-300">
            <IconAlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{t('hints.compileBlocked')}</span>
          </div>
        )}

        {groups.length === 0 && !isLoading ? (
          <div className="p-8 border border-dashed rounded-lg flex flex-col items-center justify-center text-muted-foreground bg-muted/20">
            <IconCheck className="w-8 h-8 mb-2 text-green-500/50" />
            <div>{t('empty')}</div>
          </div>
        ) : filteredGroups.length === 0 && !isLoading ? (
          <div className="p-8 border border-dashed rounded-lg flex flex-col items-center justify-center text-muted-foreground bg-muted/20">
            <IconCheck className="w-8 h-8 mb-2 text-green-500/50" />
            <div>{t('emptyFiltered')}</div>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredGroups.map((group) => (
              <div key={group.group_id} className="border rounded-lg overflow-hidden bg-card">
                <div className="flex items-center justify-between p-4 bg-muted/30 border-b gap-3 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className={tierBadgeClass(group.tier)}>
                      {t(`tiers.${group.tier}`)}
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {t('groupLabel', { id: group.group_id })}
                    </span>
                    {group.status === 'deferred' && (
                      <Badge variant="outline">{t('status.deferred')}</Badge>
                    )}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleToggleSnippets(group.group_id)}
                      data-testid={`wiki-dedup-snippet-btn-${group.group_id}`}
                    >
                      {snippetLoadingGroupId === group.group_id
                        ? t('snippets.loading')
                        : expandedSnippetGroupId === group.group_id
                          ? t('snippets.hide')
                          : t('snippets.show')}
                    </Button>
                    {activeGroupId === group.group_id && pendingAction ? (
                      <>
                        <Button size="sm" variant="outline" onClick={cancelDisposition} disabled={isApplying}>
                          {t('actions.cancel')}
                        </Button>
                        <Button size="sm" onClick={() => void handleApplyDisposition()} disabled={isApplying}>
                          {isApplying ? t('actions.applying') : t('actions.confirm')}
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => startDisposition(group.group_id, 'defer')}
                        >
                          {t('actions.defer')}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => startDisposition(group.group_id, 'dismiss')}
                        >
                          {t('actions.dismiss')}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => startDisposition(group.group_id, 'exclude')}
                        >
                          {t('actions.exclude')}
                        </Button>
                        <Button size="sm" onClick={() => startDisposition(group.group_id, 'trash')}>
                          {t('actions.trash')}
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                <div className="p-4 space-y-3 text-sm">
                  <p className="text-muted-foreground">
                    {t('recommendedKeep')}{' '}
                    <code className="rounded bg-muted px-1.5 py-0.5">{group.recommended_keep_path}</code>
                  </p>
                  {activeGroupId === group.group_id &&
                    pendingAction &&
                    (pendingAction === 'trash' || pendingAction === 'exclude') && (
                      <textarea
                        className="w-full min-h-[72px] p-3 rounded-lg border bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-y"
                        value={reasonDraft}
                        onChange={(event) => setReasonDraft(event.target.value)}
                        placeholder={t('reasonPlaceholder')}
                        spellCheck={false}
                      />
                    )}
                  <ul className="space-y-2">
                    {group.members.map((member) => (
                      <li
                        key={member.relative_path}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
                      >
                        <code className="text-xs break-all">{member.relative_path}</code>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground shrink-0">
                          <span>{t('memberModified', { time: formatMtimeNs(member.mtime_ns, locale) })}</span>
                          <span>{formatBytes(member.size_bytes)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                  {expandedSnippetGroupId === group.group_id && (
                    <div
                      className="grid gap-3 md:grid-cols-2"
                      data-testid={`wiki-dedup-snippets-${group.group_id}`}
                    >
                      {(snippetCache[group.group_id] ?? []).map((item) => (
                        <div key={item.relative_path} className="rounded-md border bg-muted/20 p-3 space-y-2">
                          <code className="text-xs break-all">{item.relative_path}</code>
                          <pre className="whitespace-pre-wrap text-xs text-muted-foreground font-mono leading-relaxed">
                            {item.snippet || t('snippets.empty')}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {(vaultHygiene.trashed.length > 0 || vaultHygiene.excluded.length > 0) && (
          <div className="space-y-4 border-t pt-4" data-testid="wiki-dedup-vault-hygiene">
            <div>
              <h3 className="text-sm font-medium">{t('vaultHygiene.title')}</h3>
              <p className="text-xs text-muted-foreground mt-1">{t('vaultHygiene.description')}</p>
            </div>

            {vaultHygiene.trashed.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">{t('vaultHygiene.trashedTitle')}</p>
                <ul className="space-y-2">
                  {vaultHygiene.trashed.map((entry) => (
                    <li
                      key={entry.relative_path}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
                    >
                      <code className="text-xs break-all">{entry.relative_path}</code>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={restoringPath === entry.relative_path}
                        onClick={() => void handleRestoreTrashed(entry.relative_path)}
                      >
                        {restoringPath === entry.relative_path
                          ? t('vaultHygiene.restoring')
                          : t('vaultHygiene.restoreTrash')}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {vaultHygiene.excluded.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">{t('vaultHygiene.excludedTitle')}</p>
                <ul className="space-y-2">
                  {vaultHygiene.excluded.map((entry) => (
                    <li
                      key={entry.relative_path}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
                    >
                      <div className="min-w-0 space-y-1">
                        <code className="text-xs break-all">{entry.relative_path}</code>
                        {entry.reason && (
                          <p className="text-xs text-muted-foreground break-words">{entry.reason}</p>
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={restoringPath === entry.relative_path}
                        onClick={() => void handleUndoExcluded(entry.relative_path)}
                      >
                        {restoringPath === entry.relative_path
                          ? t('vaultHygiene.restoring')
                          : t('vaultHygiene.restoreExclude')}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { formatDistanceToNow } from 'date-fns';
import { zhCN, enUS } from 'date-fns/locale';
import { ChevronDown, GitCompare, History, Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils/classnameUtils';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { toast } from '@/hooks/useToast';
import { LazyMonacoDiffEditor as DiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import {
  compareSkillVersions,
  listSkillVersions,
  rollbackSkillVersion,
  type SkillVersionSummary,
} from '@/services/skill-optimization';

interface SkillVersionsPanelProps {
  skillId: string;
  onActivated?: () => void;
  className?: string;
}

export function SkillVersionsPanel({ skillId, onActivated, className }: SkillVersionsPanelProps) {
  const t = useTranslations('settings.skillOptimization.versions');
  const tSkills = useTranslations('settings.skills');
  const localeKey = useTranslations('settings.skills.history');
  const locale = localeKey('locale') === 'zh' ? zhCN : enUS;
  const { theme } = useTheme();

  const [versions, setVersions] = useState<SkillVersionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [comparePair, setComparePair] = useState<{ v1: number; v2: number } | null>(null);
  const [diffContent, setDiffContent] = useState<{ original: string; modified: string } | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [pendingRollback, setPendingRollback] = useState<number | null>(null);
  const [isRollingBack, setIsRollingBack] = useState(false);

  const fetchVersions = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listSkillVersions(skillId);
      setVersions(data.versions);
    } catch {
      setVersions([]);
    } finally {
      setIsLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    void fetchVersions();
  }, [fetchVersions]);

  const handleCompare = async (left: number, right: number) => {
    const v1 = Math.min(left, right);
    const v2 = Math.max(left, right);
    setIsComparing(true);
    setComparePair({ v1, v2 });
    try {
      const data = await compareSkillVersions(skillId, v1, v2);
      setDiffContent({ original: data.v1.content, modified: data.v2.content });
    } catch {
      toast({ title: t('rollbackFailed'), variant: 'destructive' });
      setComparePair(null);
    } finally {
      setIsComparing(false);
    }
  };

  const handleRollback = async (version: number) => {
    setIsRollingBack(true);
    try {
      await rollbackSkillVersion(skillId, version);
      toast({ title: t('rollbackSuccess', { version }) });
      await fetchVersions();
      onActivated?.();
    } catch {
      toast({ title: t('rollbackFailed'), variant: 'destructive' });
    } finally {
      setIsRollingBack(false);
      setPendingRollback(null);
    }
  };

  const activeVersion = versions.find((v) => v.is_active);

  return (
    <div className={cn('rounded-xl border border-border/60 bg-card/40 overflow-hidden', className)}>
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 p-3 sm:p-4 text-left hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-primary/10 shrink-0">
            <History className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-medium text-sm truncate">{t('title')}</p>
            {activeVersion && (
              <p className="text-xs text-muted-foreground truncate">
                v{activeVersion.version} · {t('active')}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            title={t('refresh')}
            disabled={isLoading}
            onClick={(e) => {
              e.stopPropagation();
              void fetchVersions();
            }}
          >
            <RefreshCw className={cn('h-4 w-4 text-muted-foreground', isLoading && 'animate-spin')} />
          </Button>
          <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border/50 px-3 pb-3 sm:px-4 sm:pb-4 space-y-3">
          {isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : versions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">{t('noVersions')}</p>
          ) : (
            <ul className="space-y-2 max-h-48 sm:max-h-56 overflow-y-auto">
              {versions.map((v) => (
                <li
                  key={v.version}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 rounded-lg border border-border/40 bg-background/50 p-2.5 sm:p-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-sm font-medium">v{v.version}</span>
                      {v.is_active && (
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                          {t('active')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {formatDistanceToNow(new Date(v.created_at), { addSuffix: true, locale })} · {v.created_by}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {activeVersion && v.version !== activeVersion.version && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 px-2 text-xs"
                        disabled={isComparing}
                        onClick={() => void handleCompare(activeVersion.version, v.version)}
                      >
                        <GitCompare className="h-3.5 w-3.5 mr-1" />
                        {t('compare')}
                      </Button>
                    )}
                    {!v.is_active && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-8 px-2 text-xs"
                        onClick={() => setPendingRollback(v.version)}
                      >
                        <RotateCcw className="h-3.5 w-3.5 mr-1" />
                        {t('rollback')}
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {comparePair && diffContent && (
            <div className="rounded-lg border border-border/50 overflow-hidden">
              <p className="text-xs text-muted-foreground px-3 py-2 border-b bg-muted/20">
                {t('comparing', { v1: comparePair.v1, v2: comparePair.v2 })}
              </p>
              <div className="h-48 sm:h-64">
                <DiffEditor
                  original={diffContent.original}
                  modified={diffContent.modified}
                  theme={theme === 'dark' ? 'vs-dark' : 'light'}
                  options={{ readOnly: true, minimap: { enabled: false }, scrollBeyondLastLine: false }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      <AlertDialog open={pendingRollback !== null} onOpenChange={(open) => !open && setPendingRollback(null)}>
        <AlertDialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('rollback')}</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRollback !== null ? t('rollbackConfirm', { version: pendingRollback }) : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2">
            <AlertDialogCancel disabled={isRollingBack}>{tSkills('upload.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={isRollingBack || pendingRollback === null}
              onClick={() => pendingRollback !== null && void handleRollback(pendingRollback)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isRollingBack && <Loader2 className="animate-spin mr-2 h-4 w-4" />}
              {t('confirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

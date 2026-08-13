'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Check, ExternalLink, Link2Off, LinkIcon, Loader2, RefreshCw } from 'lucide-react';
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
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import {
  buildPublicArtifactShareUrl,
  fetchArtifactShares,
  formatShareTimestamp,
  revokeArtifactShare,
  type ArtifactShareRecord,
} from '@/services/artifactShares';

type LoadState = 'loading' | 'ready' | 'error';

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  html: 'type.html',
  pdf: 'type.pdf',
  document: 'type.document',
};

export default function ShareLinksSection() {
  const t = useTranslations('settings.shares');
  const locale = useLocale();
  const [records, setRecords] = useState<ArtifactShareRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<ArtifactShareRecord | null>(null);

  const load = useCallback(async () => {
    setLoadState('loading');
    try {
      const rows = await fetchArtifactShares();
      setRecords(rows);
      setLoadState('ready');
    } catch (err) {
      setLoadState('error');
      toast.error(err instanceof Error ? err.message : t('loadError'));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRevoke = useCallback(
    async (record: ArtifactShareRecord) => {
      setRevokingId(record.id);
      try {
        await revokeArtifactShare(record.id);
        setRecords((prev) => prev.filter((r) => r.id !== record.id));
        toast.success(t('revokeSuccess'));
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('revokeError'));
      } finally {
        setRevokingId(null);
        setPendingRevoke(null);
      }
    },
    [t],
  );

  const handleOpen = useCallback((record: ArtifactShareRecord) => {
    const url = record.share_url ?? record.share_path;
    if (!url) {return;}
    window.open(buildPublicArtifactShareUrl(url), '_blank', 'noopener,noreferrer');
  }, []);

  const handleCopy = useCallback(
    async (record: ArtifactShareRecord) => {
      const url = record.share_url ?? record.share_path;
      if (!url) {return;}
      try {
        await navigator.clipboard.writeText(buildPublicArtifactShareUrl(url));
        setCopiedId(record.id);
        window.setTimeout(() => {
          setCopiedId((current) => (current === record.id ? null : current));
        }, 2000);
      } catch {
        toast.error(t('copyError'));
      }
    },
    [t],
  );

  const typeLabel = (artifactType: string | null) =>
    artifactType ? t(ARTIFACT_TYPE_LABELS[artifactType] ?? 'type.unknown') : '—';

  const isRevoking = (id: string) => revokingId === id;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div className="space-y-1.5">
          <CardTitle>{t('title')}</CardTitle>
          <CardDescription>{t('description')}</CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void load()}
          disabled={loadState === 'loading'}
          aria-label={t('refresh')}
        >
          <RefreshCw className={cn('h-4 w-4', loadState === 'loading' && 'animate-spin')} />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadState === 'loading' && (
          <div className="flex items-center justify-center py-12 text-muted-foreground" data-testid="shares-loading">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        )}

        {loadState === 'error' && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center">
            <p className="text-sm text-destructive">{t('loadError')}</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
              {t('retry')}
            </Button>
          </div>
        )}

        {loadState === 'ready' && records.length === 0 && (
          <div className="rounded-xl border border-dashed border-border/60 py-12 text-center" data-testid="shares-empty">
            <Link2Off className="mx-auto h-8 w-8 text-muted-foreground/40" />
            <p className="mt-3 text-sm text-muted-foreground">{t('empty')}</p>
          </div>
        )}

        {loadState === 'ready' && records.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-border/50">
            <table className="w-full text-left text-sm" data-testid="shares-table">
              <thead className="bg-secondary/50 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('table.artifact')}</th>
                  <th className="px-4 py-3 font-medium">{t('table.type')}</th>
                  <th className="px-4 py-3 font-medium">{t('table.link')}</th>
                  <th className="px-4 py-3 font-medium">{t('table.protected')}</th>
                  <th className="px-4 py-3 font-medium">{t('table.expiresAt')}</th>
                  <th className="px-4 py-3 text-right font-medium">{t('table.action')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {records.map((record) => (
                  <tr key={record.id} className="bg-background/40 transition-colors hover:bg-secondary/30">
                    <td className="max-w-[220px] truncate px-4 py-3 font-medium text-foreground">
                      {record.artifact_name}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{typeLabel(record.artifact_type)}</td>
                    <td className="px-4 py-3">
                      {record.share_path ? (
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void handleCopy(record)}
                            aria-label={t('copyLabel', { name: record.artifact_name })}
                          >
                            {copiedId === record.id ? (
                              <Check className="h-4 w-4 text-emerald-500" />
                            ) : (
                              <LinkIcon className="h-4 w-4" />
                            )}
                            <span className="ml-1.5">{copiedId === record.id ? t('copied') : t('copy')}</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void handleOpen(record)}
                            aria-label={t('openLabel', { name: record.artifact_name })}
                          >
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">{t('linkProtected')}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{record.password_protected ? t('yes') : t('no')}</td>
                    <td className="px-4 py-3 text-muted-foreground">{formatShareTimestamp(record.expires_at, locale)}</td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={isRevoking(record.id)}
                        onClick={() => setPendingRevoke(record)}
                        aria-label={t('revokeLabel', { name: record.artifact_name })}
                      >
                        {isRevoking(record.id) ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Link2Off className="h-4 w-4" />
                        )}
                        <span className="ml-1.5">{t('revoke')}</span>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <AlertDialog open={pendingRevoke !== null} onOpenChange={(open) => !open && setPendingRevoke(null)}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirm.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirm.description', { name: pendingRevoke?.artifact_name ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {pendingRevoke && (
            <div className="space-y-2 rounded-lg border border-border/50 bg-muted/30 p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t('table.artifact')}</span>
                <span className="max-w-[60%] truncate font-medium text-foreground">
                  {pendingRevoke.artifact_name}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t('table.type')}</span>
                <span className="text-foreground">{typeLabel(pendingRevoke.artifact_type)}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t('confirm.createdAt')}</span>
                <span className="text-foreground">{formatShareTimestamp(pendingRevoke.created_at, locale)}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t('table.expiresAt')}</span>
                <span className="text-foreground">{formatShareTimestamp(pendingRevoke.expires_at, locale)}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t('table.protected')}</span>
                <span className="text-foreground">
                  {pendingRevoke.password_protected ? t('yes') : t('no')}
                </span>
              </div>
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>{t('confirm.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className={cn('bg-destructive text-destructive-foreground hover:bg-destructive/90')}
              disabled={pendingRevoke === null || isRevoking(pendingRevoke.id)}
              onClick={() => pendingRevoke && void handleRevoke(pendingRevoke)}
            >
              {pendingRevoke && isRevoking(pendingRevoke.id) ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Link2Off className="h-4 w-4" />
              )}
              <span className="ml-1.5">{t('confirm.revoke')}</span>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

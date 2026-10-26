'use client';

/**
 * [INPUT]
 * @/services/wiki/ima::listImaItems (POS: per-bucket item report)
 * ./imaCopy::imaReasonKey, imaNoteKeys, imaKindKey, imaErrorKey (POS: server code → locale key)
 *
 * [OUTPUT]
 * ImaReportDialog: what did not import cleanly, grouped as needs-attention / simplified / removed in ima
 *
 * [POS]
 * Detail view behind the ima card's counts; the card mounts it only while open, so every opening starts on the first bucket with items. Each row says what happened in plain words (the server sends codes only),
 * so a user can tell "ima has no readable text for this" from "try again later" and act on the latter.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Skeleton } from '@/components/primitives/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { listImaItems, type ImaItemBucket, type ImaItemCounts, type ImaItemView } from '@/services/wiki/ima';
import { imaAttentionCount, imaErrorKey, imaKindKey, imaNoteKeys, imaReasonKey } from './imaCopy';

interface ImaReportDialogProps {
  onOpenChange: (open: boolean) => void;
  agentId: string | null;
  counts: ImaItemCounts;
  retrying: boolean;
  onRetryFailed: () => void;
}

type BucketState = { kind: 'loading' } | { kind: 'ready'; items: ImaItemView[] } | { kind: 'failed'; errorKey: string };

const BUCKETS: readonly ImaItemBucket[] = ['attention', 'lossy', 'remote_deleted'];

function bucketCount(bucket: ImaItemBucket, counts: ImaItemCounts): number {
  switch (bucket) {
    case 'attention':
      return imaAttentionCount(counts);
    case 'lossy':
      return counts.partial;
    case 'remote_deleted':
      return counts.remote_deleted;
  }
}

function firstNonEmpty(counts: ImaItemCounts): ImaItemBucket {
  return BUCKETS.find((bucket) => bucketCount(bucket, counts) > 0) ?? 'attention';
}

export default function ImaReportDialog({
  onOpenChange,
  agentId,
  counts,
  retrying,
  onRetryFailed,
}: ImaReportDialogProps) {
  const t = useTranslations('settings.wiki.ima');
  const [bucket, setBucket] = useState<ImaItemBucket>(() => firstNonEmpty(counts));
  const [state, setState] = useState<BucketState>({ kind: 'loading' });

  const load = useCallback(
    async (target: ImaItemBucket) => {
      setState({ kind: 'loading' });
      try {
        setState({ kind: 'ready', items: await listImaItems(target, agentId) });
      } catch (error) {
        setState({ kind: 'failed', errorKey: imaErrorKey(error) });
      }
    },
    [agentId],
  );

  useEffect(() => {
    void load(bucket);
  }, [bucket, load]);

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[calc(100vw-2rem)] max-w-2xl flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{t('report.title')}</DialogTitle>
          <DialogDescription>{t(`report.hint.${bucket}`)}</DialogDescription>
        </DialogHeader>

        <Tabs value={bucket} onValueChange={(value) => setBucket(value as ImaItemBucket)}>
          <TabsList className="grid w-full grid-cols-3">
            {BUCKETS.map((entry) => (
              <TabsTrigger key={entry} value={entry} className="gap-1.5 px-2">
                <span className="truncate">{t(`report.tabs.${entry}`)}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{bucketCount(entry, counts)}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {bucket === 'attention' && counts.failed > 0 ? (
          <div>
            <Button type="button" size="sm" variant="outline" disabled={retrying} onClick={onRetryFailed}>
              {t('report.retryFailed', { count: counts.failed })}
            </Button>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {state.kind === 'loading' ? (
            <div className="space-y-2" aria-busy="true">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          ) : null}
          {state.kind === 'failed' ? (
            <p role="alert" className="text-sm text-destructive">
              {t(state.errorKey)}
            </p>
          ) : null}
          {state.kind === 'ready' && state.items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t('report.empty')}</p>
          ) : null}
          {state.kind === 'ready' && state.items.length > 0 ? (
            <ul className="space-y-2">
              {state.items.map((item, index) => (
                <ReportRow key={`${item.container_name}/${item.folder_path}/${item.title}/${index}`} item={item} />
              ))}
            </ul>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReportRow({ item }: { item: ImaItemView }) {
  const t = useTranslations('settings.wiki.ima');
  const where = [item.container_name, item.folder_path].filter(Boolean).join(' / ');
  const detail =
    item.status === 'remote_deleted'
      ? []
      : item.status === 'synced'
        ? imaNoteKeys(item.notes)
        : [imaReasonKey(item.reason)];

  return (
    <li className="rounded-lg border border-border/60 bg-background/40 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 break-words text-sm font-medium" title={item.title}>
          {item.title}
        </p>
        {item.media_kind ? (
          <Badge variant="outline" className="shrink-0 font-normal">
            {t(imaKindKey(item.media_kind))}
          </Badge>
        ) : null}
      </div>
      {where ? <p className="mt-0.5 truncate text-xs text-muted-foreground">{where}</p> : null}
      {detail.map((key) => (
        <p
          key={key}
          className={item.status === 'failed' ? 'mt-1 text-xs text-warning' : 'mt-1 text-xs text-muted-foreground'}
        >
          {t(key)}
        </p>
      ))}
    </li>
  );
}

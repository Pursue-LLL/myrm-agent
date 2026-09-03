'use client';

/**
 * [INPUT]
 * - @/services/memory/externalTranscripts (POS: 外部 Agent 会话同步 API 客户端)
 * - next-intl::useTranslations (POS: 多语言国际化钩子)
 *
 * [OUTPUT]
 * - ExternalHarnessSyncCard: External agent transcript recall management card.
 *
 * [POS]
 * 外部 Agent 会话召回管理卡片。提供本地目录增量同步与浏览器端目录一键选择上传。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, FolderSync, Loader2, RefreshCw, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/shared/useToast';
import {
  getExternalTranscriptStatus,
  syncExternalTranscripts,
  type ExternalFilePayload,
  type ExternalTranscriptStatus,
} from '@/services/memory/externalTranscripts';

interface FileSystemEntryLike {
  kind: 'file' | 'directory';
  name: string;
  getFile?(): Promise<File>;
  values?(): AsyncIterable<FileSystemEntryLike>;
}

interface WindowWithDirectoryPicker {
  showDirectoryPicker?: () => Promise<FileSystemEntryLike>;
}

const ExternalHarnessSyncCard = memo(() => {
  const t = useTranslations('memory.externalHarness');
  const [status, setStatus] = useState<ExternalTranscriptStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await getExternalTranscriptStatus();
      setStatus(data);
    } catch (err) {
      // Non-fatal if server has no watermarks yet
      setStatus(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleIncrementalSync = useCallback(async () => {
    try {
      setIsSyncing(true);
      const res = await syncExternalTranscripts({});
      if (res.errors && res.errors.length > 0) {
        toast({
          title: t('syncPartialWarning'),
          description: res.errors.join('; '),
          variant: 'destructive',
        });
      } else {
        toast({
          title: t('syncSuccess'),
          description: t('syncSuccessDesc', {
            files: res.synced_files,
            turns: res.new_turns,
          }),
        });
      }
      await fetchStatus();
    } catch (err) {
      toast({
        title: t('syncFailed'),
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setIsSyncing(false);
    }
  }, [fetchStatus, t]);

  const handlePickLocalDirectory = useCallback(async () => {
    const win = window as unknown as WindowWithDirectoryPicker;
    if (!win.showDirectoryPicker) {
      toast({
        title: t('browserNotSupported'),
        description: t('browserNotSupportedDesc'),
        variant: 'destructive',
      });
      return;
    }

    try {
      setIsSyncing(true);
      const dirHandle = await win.showDirectoryPicker();
      const files: ExternalFilePayload[] = [];

      // Recursively traverse directory for .jsonl files
      async function traverse(handle: FileSystemEntryLike, prefix = '') {
        if (!handle.values) {
          return;
        }
        for await (const entry of handle.values()) {
          if (entry.kind === 'file' && entry.name.endsWith('.jsonl') && entry.getFile) {
            const file = await entry.getFile();
            const content = await file.text();
            files.push({
              filename: prefix ? `${prefix}/${entry.name}` : entry.name,
              content,
            });
          } else if (entry.kind === 'directory') {
            await traverse(entry, prefix ? `${prefix}/${entry.name}` : entry.name);
          }
        }
      }

      await traverse(dirHandle);

      if (files.length === 0) {
        toast({
          title: t('noJsonlFound'),
          description: t('noJsonlFoundDesc'),
        });
        return;
      }

      const res = await syncExternalTranscripts({
        uploaded_files: files,
      });

      toast({
        title: t('syncSuccess'),
        description: t('syncSuccessDesc', {
          files: res.synced_files,
          turns: res.new_turns,
        }),
      });
      await fetchStatus();
    } catch (err: unknown) {
      if (typeof err === 'object' && err !== null && 'name' in err && (err as { name: string }).name === 'AbortError') {
        return;
      }
      const message = err instanceof Error ? err.message : String(err);
      toast({
        title: t('syncFailed'),
        description: message,
        variant: 'destructive',
      });
    } finally {
      setIsSyncing(false);
    }
  }, [fetchStatus, t]);

  return (
    <div className="rounded-xl border border-border/60 bg-card/60 p-4 shadow-sm backdrop-blur-sm transition-all hover:border-border">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2 text-primary">
            <Terminal className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                {t('activeBadge')}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{t('description')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-center">
          <button
            type="button"
            onClick={handlePickLocalDirectory}
            disabled={isSyncing}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            <FolderSync className="h-3.5 w-3.5" />
            <span>{t('pickDirectoryBtn')}</span>
          </button>

          <button
            type="button"
            onClick={handleIncrementalSync}
            disabled={isSyncing}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {isSyncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span>{t('syncNowBtn')}</span>
          </button>
        </div>
      </div>

      <div className="mt-3.5 grid grid-cols-1 gap-2 border-t border-border/40 pt-3 text-[11px] text-muted-foreground sm:grid-cols-3">
        <div className="flex items-center gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
          <span>
            {t('trackedFiles')}: <strong className="text-foreground">{status?.tracked_files_count ?? 0}</strong>
          </span>
        </div>
        <div className="truncate">
          <span>
            {t('defaultPath')}:{' '}
            <code className="text-[10px] text-foreground/80">{status?.default_directory ?? '~/.claude/projects'}</code>
          </span>
        </div>
        <div className="sm:text-right">
          <span>
            {t('lastSynced')}:{' '}
            {status?.last_synced_at ? new Date(status.last_synced_at).toLocaleString() : t('neverSynced')}
          </span>
        </div>
      </div>
    </div>
  );
});

ExternalHarnessSyncCard.displayName = 'ExternalHarnessSyncCard';

export default ExternalHarnessSyncCard;

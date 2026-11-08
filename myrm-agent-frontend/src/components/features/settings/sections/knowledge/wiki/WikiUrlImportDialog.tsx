'use client';

import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { wikiService, type ImportUrlsResultResponse, type UrlImportItemResult } from '@/services/wikiService';

interface WikiUrlImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentScopeId?: string | null;
  onImportFinished: (result: ImportUrlsResultResponse) => void;
}

export function WikiUrlImportDialog({ open, onOpenChange, agentScopeId, onImportFinished }: WikiUrlImportDialogProps) {
  const t = useTranslations('settings.wiki.import');
  const [urlText, setUrlText] = useState('');
  const [folderPath, setFolderPath] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [failures, setFailures] = useState<UrlImportItemResult[]>([]);

  const parsedUrls = useMemo(() => {
    const rawLines = urlText.split('\n');
    const seen = new Set<string>();
    const valid: string[] = [];
    for (const raw of rawLines) {
      const line = raw.trim();
      if (!line) {
        continue;
      }
      if (!/^https?:\/\//i.test(line)) {
        continue;
      }
      if (!seen.has(line)) {
        seen.add(line);
        valid.push(line);
      }
    }
    return valid;
  }, [urlText]);

  // A failure stops being listed once its link is edited or removed from the box.
  const listedFailures = useMemo(
    () => failures.filter((item) => parsedUrls.includes(item.url)),
    [failures, parsedUrls],
  );

  const handleClose = () => {
    if (isSubmitting) {
      return;
    }
    setUrlText('');
    setFolderPath('');
    setFailures([]);
    onOpenChange(false);
  };

  const handleSubmit = async () => {
    if (parsedUrls.length === 0) {
      toast.error(t('urlImportEmptyError'));
      return;
    }
    const finalUrls = parsedUrls.slice(0, 50);
    if (parsedUrls.length > 50) {
      toast.warning(t('urlImportTooManyError'));
    }

    setIsSubmitting(true);
    try {
      const res = await wikiService.importUrls(finalUrls, folderPath.trim() || undefined, true, agentScopeId);
      const summary = t('urlImportResult', {
        total: res.total_urls,
        enqueued: res.enqueued_count,
        errors: res.error_count,
      });
      onImportFinished(res);
      // The box keeps what still needs importing (links that could not be read, links beyond this batch's
      // limit), so one more click continues with just those.
      const failed = res.results.filter((item) => item.status === 'error');
      const remaining = [...failed.map((item) => item.url), ...parsedUrls.slice(finalUrls.length)];
      if (failed.length > 0) {
        toast.warning(summary);
      } else {
        toast.success(summary);
      }
      if (remaining.length === 0) {
        handleClose();
        return;
      }
      setFailures(failed);
      setUrlText(remaining.join('\n'));
    } catch (err) {
      console.error('URL batch import failed:', err);
      toast.error(t('importFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : handleClose())}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-[560px] sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t('urlImportTitle')}</DialogTitle>
          <DialogDescription>{t('urlImportDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t('urlImportCount', { count: Math.min(parsedUrls.length, 50) })}</span>
              {parsedUrls.length > 50 ? (
                <span className="text-amber-600 dark:text-amber-400 font-medium">{t('urlImportTooManyError')}</span>
              ) : null}
            </div>
            <Textarea
              value={urlText}
              onChange={(e) => setUrlText(e.target.value)}
              placeholder={t('urlImportPlaceholder')}
              rows={6}
              disabled={isSubmitting}
              className="font-mono text-xs resize-none"
            />
            {listedFailures.length > 0 ? (
              <div
                role="alert"
                className="space-y-1.5 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs"
              >
                <p className="font-medium text-destructive-text">{t('urlImportFailedHint')}</p>
                <ul className="max-h-32 space-y-1 overflow-y-auto">
                  {listedFailures.map((item) => (
                    <li key={item.url} className="break-all">
                      <span className="font-mono text-foreground">{item.url}</span>
                      {item.error ? <span className="text-muted-foreground"> - {item.error}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">{t('urlImportFolderLabel')}</label>
            <Input
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder={t('urlImportFolderPlaceholder')}
              disabled={isSubmitting}
              className="text-xs"
            />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
            {t('conflictKeepSkipped')}
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting || parsedUrls.length === 0}>
            {isSubmitting ? t('urlImporting') : t('urlImportStart')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

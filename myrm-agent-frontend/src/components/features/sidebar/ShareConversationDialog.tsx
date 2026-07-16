'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Copy, Info, Link2, Loader2, Unlink } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { isLocalMode } from '@/lib/deploy-mode';

interface ShareConversationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shareUrl: string | null;
  expiresAt: number | null;
  loading: boolean;
  onCreateLink: (ttlDays: number) => void;
  onRevoke: () => void;
}

export function ShareConversationDialog({
  open,
  onOpenChange,
  shareUrl,
  expiresAt,
  loading,
  onCreateLink,
  onRevoke,
}: ShareConversationDialogProps) {
  const t = useTranslations();
  const [copied, setCopied] = useState(false);
  const [ttlDays] = useState(7);
  const isLocal = isLocalMode();

  const handleCopy = useCallback(async () => {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [shareUrl]);

  const expiresDate = expiresAt ? new Date(expiresAt * 1000).toLocaleDateString() : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 size={18} />
            {t('chat.share.title')}
          </DialogTitle>
          <DialogDescription>{t('chat.share.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {isLocal && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
              <Info size={16} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
              <p className="text-xs text-amber-700 dark:text-amber-300">{t('chat.share.localFallback')}</p>
            </div>
          )}
          {shareUrl ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={shareUrl}
                  className="flex-1 rounded-md border bg-muted px-3 py-2 text-sm font-mono truncate"
                />
                <Button size="sm" variant="outline" onClick={handleCopy} className="shrink-0">
                  {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                  <span className="ml-1.5">{copied ? t('chat.share.copied') : t('chat.share.copyLink')}</span>
                </Button>
              </div>
              {expiresDate && (
                <p className="text-xs text-muted-foreground">
                  {t('chat.share.expires')}: {expiresDate}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('chat.share.description')}</p>
          )}
        </div>

        <DialogFooter className="flex-row gap-2 sm:justify-between">
          {shareUrl ? (
            <Button variant="destructive" size="sm" onClick={onRevoke}>
              <Unlink size={14} className="mr-1.5" />
              {t('chat.share.revoke')}
            </Button>
          ) : (
            <Button onClick={() => onCreateLink(ttlDays)} disabled={loading}>
              {loading && <Loader2 size={14} className="mr-1.5 animate-spin" />}
              {loading ? t('chat.share.creating') : t('chat.share.createLink')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

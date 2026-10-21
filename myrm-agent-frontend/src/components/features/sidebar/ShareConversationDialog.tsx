'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Copy, Info, Link2, Loader2, Lock, Unlink } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
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
  revoked: boolean;
  passwordProtected: boolean;
  loading: boolean;
  onCreateLink: (ttlDays: number, password?: string) => void;
  onRevoke: () => void;
}

export function ShareConversationDialog({
  open,
  onOpenChange,
  shareUrl,
  expiresAt,
  revoked,
  passwordProtected,
  loading,
  onCreateLink,
  onRevoke,
}: ShareConversationDialogProps) {
  const t = useTranslations();
  const [copied, setCopied] = useState(false);
  const [ttlDays, setTtlDays] = useState(7);
  const [password, setPassword] = useState('');
  const isLocal = isLocalMode();

  const handleCopy = useCallback(async () => {
    if (!shareUrl) {
      return;
    }
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [shareUrl]);

  const handleCreate = useCallback(() => {
    const pwd = password.trim() || undefined;
    onCreateLink(ttlDays, pwd);
  }, [onCreateLink, ttlDays, password]);

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
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-6">
              <Loader2 size={18} className="animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">{t('chat.share.loading')}</span>
            </div>
          ) : shareUrl ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Input readOnly value={shareUrl} className="h-8 flex-1 truncate font-mono text-sm" />
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
          ) : passwordProtected ? (
            <div className="flex items-start gap-2 rounded-md border bg-muted p-3">
              <Lock size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">{t('chat.share.passwordProtectedStatus')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {revoked && (
                <div className="flex items-start gap-2 rounded-md border bg-muted p-3">
                  <Unlink size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
                  <p className="text-xs text-muted-foreground">{t('chat.share.revokedStatus')}</p>
                </div>
              )}
              <div className="space-y-1.5">
                <Label className="text-xs flex items-center gap-1">
                  <Lock size={12} />
                  {t('chat.share.passwordLabel')}
                </Label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('chat.share.passwordPlaceholder')}
                  className="h-8 text-sm"
                  autoComplete="new-password"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t('chat.share.ttlLabel')}</Label>
                <div className="flex gap-1.5">
                  {[1, 7, 14, 30].map((d) => (
                    <Button
                      key={d}
                      variant={ttlDays === d ? 'default' : 'outline'}
                      size="sm"
                      className="h-7 flex-1 text-xs px-0"
                      onClick={() => setTtlDays(d)}
                    >
                      {t('chat.share.ttlDays', { days: d })}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="flex-row gap-2 sm:justify-between">
          {shareUrl || passwordProtected ? (
            <Button variant="destructive" size="sm" onClick={onRevoke}>
              <Unlink size={14} className="mr-1.5" />
              {t('chat.share.revoke')}
            </Button>
          ) : (
            <Button onClick={handleCreate} disabled={loading}>
              {loading && <Loader2 size={14} className="mr-1.5 animate-spin" />}
              {loading ? t('chat.share.creating') : t('chat.share.createLink')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

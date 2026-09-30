'use client';

/**
 * [INPUT]
 * - hostAlias: string (Target SSH host)
 * - isOpen: boolean, onClose: () => void
 * - @/services/sshVault::requestBreakGlassToken (POS: Break-glass API caller)
 *
 * [OUTPUT]
 * - BreakGlassModal: Dialog for requesting temporary emergency break-glass tokens.
 *
 * [POS]
 * Security gate modal in settings credentials SSH vault.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
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
import { Label } from '@/components/primitives/label';
import { toast } from '@/hooks/shared/useToast';
import { Check, Copy, Key, ShieldWarning } from '@phosphor-icons/react';
import { requestBreakGlassToken, type BreakGlassResponse } from '@/services/sshVault';

interface BreakGlassModalProps {
  isOpen: boolean;
  onClose: () => void;
  hostAlias: string;
}

export function BreakGlassModal({ isOpen, onClose, hostAlias }: BreakGlassModalProps) {
  const t = useTranslations('settings.sshVault');
  const [command, setCommand] = useState('');
  const [reason, setReason] = useState('');
  const [ttlSeconds, setTtlSeconds] = useState(300);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [issuedResult, setIssuedResult] = useState<BreakGlassResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const handleReset = () => {
    setCommand('');
    setReason('');
    setTtlSeconds(300);
    setIssuedResult(null);
    setCopied(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim() || !reason.trim()) {
      return;
    }

    try {
      setIsSubmitting(true);
      const res = await requestBreakGlassToken({
        host_alias: hostAlias,
        command: command.trim(),
        reason: reason.trim(),
        ttl_seconds: ttlSeconds,
      });
      setIssuedResult(res);
      toast({
        title: t('breakGlassSuccess'),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast({
        title: msg,
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyToken = async () => {
    if (!issuedResult?.token) return;
    try {
      await navigator.clipboard.writeText(issuedResult.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({
        title: t('copyFailed'),
        variant: 'destructive',
      });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="max-w-md sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldWarning className="h-5 w-5 text-amber-500" />
            {t('breakGlassModalTitle')} ({hostAlias})
          </DialogTitle>
          <DialogDescription>{t('readOnlyDesc')}</DialogDescription>
        </DialogHeader>

        {issuedResult ? (
          <div className="space-y-4 py-2">
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
              <div className="font-medium text-emerald-600 dark:text-emerald-400 mb-1">{t('breakGlassSuccess')}</div>
              <p className="text-xs text-muted-foreground mb-3">
                Host: <span className="font-mono font-semibold">{issuedResult.host_alias}</span> | Expires:{' '}
                {new Date(issuedResult.expires_at * 1000).toLocaleTimeString()}
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 font-mono text-xs bg-background/80 p-2 rounded border break-all select-all">
                  {issuedResult.token}
                </code>
                <Button size="sm" variant="outline" onClick={handleCopyToken} className="shrink-0 gap-1.5">
                  {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                  {copied ? t('copied') : t('copyPrompt')}
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleClose}>{t('done')}</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="bg-command">{t('breakGlassCommand')}</Label>
              <Input
                id="bg-command"
                placeholder="e.g. systemctl restart nginx"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                required
                className="font-mono text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="bg-reason">{t('breakGlassReason')}</Label>
              <Textarea
                id="bg-reason"
                placeholder={t('breakGlassReasonPlaceholder')}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
                rows={3}
                className="text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="bg-ttl">{t('breakGlassTtl')}</Label>
              <Input
                id="bg-ttl"
                type="number"
                min={30}
                max={1800}
                value={ttlSeconds}
                onChange={(e) => setTtlSeconds(Number(e.target.value) || 300)}
                className="font-mono text-sm"
              />
            </div>

            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="outline" onClick={handleClose}>
                {t('cancel')}
              </Button>
              <Button type="submit" disabled={isSubmitting || !command.trim() || !reason.trim()} className="gap-1.5">
                <Key className="h-4 w-4" />
                {t('breakGlassSubmit')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

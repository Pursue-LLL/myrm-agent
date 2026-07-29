'use client';

import { useTranslations } from 'next-intl';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';

interface WikiImportSecurityDialogProps {
  open: boolean;
  blockedPaths: string[];
  redactedPaths: string[];
  onClose: () => void;
}

export function WikiImportSecurityDialog({
  open,
  blockedPaths,
  redactedPaths,
  onClose,
}: WikiImportSecurityDialogProps) {
  const t = useTranslations('settings.wiki.import');

  const previewBlocked = blockedPaths.slice(0, 8);
  const previewRedacted = redactedPaths.slice(0, 8);
  const blockedRemaining = blockedPaths.length - previewBlocked.length;
  const redactedRemaining = redactedPaths.length - previewRedacted.length;

  return (
    <AlertDialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-[520px] sm:max-w-[520px]">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('securityTitle')}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-4 text-sm text-muted-foreground">
              {blockedPaths.length > 0 ? (
                <div className="space-y-2">
                  <p>{t('securityBlockedDescription', { count: blockedPaths.length })}</p>
                  <ul className="max-h-32 list-disc space-y-1 overflow-y-auto pl-5 font-mono text-xs text-foreground/80">
                    {previewBlocked.map((path) => (
                      <li key={`blocked-${path}`}>{path}</li>
                    ))}
                  </ul>
                  {blockedRemaining > 0 ? (
                    <p className="text-xs">{t('securityMore', { count: blockedRemaining })}</p>
                  ) : null}
                </div>
              ) : null}
              {redactedPaths.length > 0 ? (
                <div className="space-y-2">
                  <p>{t('securityRedactedDescription', { count: redactedPaths.length })}</p>
                  <ul className="max-h-32 list-disc space-y-1 overflow-y-auto pl-5 font-mono text-xs text-foreground/80">
                    {previewRedacted.map((path) => (
                      <li key={`redacted-${path}`}>{path}</li>
                    ))}
                  </ul>
                  {redactedRemaining > 0 ? (
                    <p className="text-xs">{t('securityMore', { count: redactedRemaining })}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction onClick={onClose}>{t('securityAcknowledge')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

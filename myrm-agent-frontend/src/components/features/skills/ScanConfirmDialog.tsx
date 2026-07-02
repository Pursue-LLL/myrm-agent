'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Badge } from '@/components/primitives/badge';
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
import type { DiscoveryPreviewResponse } from '@/services/skill';

const SEVERITY_COLORS: Record<number, string> = {
  1: 'text-yellow-500',
  2: 'text-orange-500',
  3: 'text-red-500',
  4: 'text-red-700 dark:text-red-400',
};

const SEVERITY_LABELS: Record<number, string> = {
  1: 'LOW',
  2: 'MEDIUM',
  3: 'HIGH',
  4: 'CRITICAL',
};

interface ScanConfirmDialogProps {
  open: boolean;
  previewResult: DiscoveryPreviewResponse | null;
  onConfirm: () => void;
  onCancel: () => void;
}

const ScanConfirmDialog = memo(({ open, previewResult, onConfirm, onCancel }: ScanConfirmDialogProps) => {
  const t = useTranslations('settings.skills.discover');

  if (!previewResult) return null;

  return (
    <AlertDialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-500" />
            {t('scanWarningTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3">
              <p>
                {t('scanWarningDesc', {
                  name: previewResult.name,
                  count: previewResult.scan_findings.length,
                })}
              </p>
              <div className="space-y-2 max-h-48 overflow-y-auto rounded-md border p-3 bg-muted/30">
                {previewResult.scan_findings.map((finding, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-sm">
                    <Badge
                      variant="outline"
                      className={cn('text-[10px] shrink-0 mt-0.5', SEVERITY_COLORS[finding.severity])}
                    >
                      {SEVERITY_LABELS[finding.severity] ?? 'UNKNOWN'}
                    </Badge>
                    <span className="text-foreground">
                      {finding.line_number != null && (
                        <span className="font-mono text-[11px] text-muted-foreground mr-1">
                          L{finding.line_number}
                        </span>
                      )}
                      {finding.description}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('scanCancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} className="bg-amber-600 hover:bg-amber-700 text-white">
            <ShieldCheck className="h-4 w-4 mr-1.5" />
            {t('scanConfirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
});

ScanConfirmDialog.displayName = 'ScanConfirmDialog';
export default ScanConfirmDialog;

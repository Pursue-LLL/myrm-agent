'use client';

import { IconShield } from '@/components/features/icons/PremiumIcons';
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
import { cn } from '@/lib/utils/classnameUtils';
import { getMcpFindingDescription, getMcpFindingRecommendation } from '@/lib/utils/mcpScanFindingText';
import type { MCPScanFinding } from '@/store/config/types';
import { useTranslations } from 'next-intl';

interface MCPScanAckDialogProps {
  open: boolean;
  serverName: string;
  findings: MCPScanFinding[];
  onConfirm: () => void;
  onCancel: () => void;
}

function severityLabel(severity: string): string {
  return severity.toUpperCase();
}

function severityClass(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'text-red-700 dark:text-red-400 border-red-300 dark:border-red-800';
    case 'high':
      return 'text-orange-600 dark:text-orange-400 border-orange-300 dark:border-orange-800';
    case 'medium':
      return 'text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-800';
    case 'low':
      return 'text-yellow-600 dark:text-yellow-400 border-yellow-300 dark:border-yellow-800';
    default:
      return 'text-muted-foreground border-border';
  }
}

export function MCPScanAckDialog({
  open,
  serverName,
  findings,
  onConfirm,
  onCancel,
}: MCPScanAckDialogProps) {
  const t = useTranslations('settings');

  return (
    <AlertDialog open={open} onOpenChange={(value) => !value && onCancel()}>
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <IconShield className="h-5 w-5 text-orange-500" />
            {t('mcpScanAckTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3">
              <p>{t('mcpScanAckDesc', { name: serverName, count: findings.length })}</p>
              <div className="space-y-2 max-h-52 overflow-y-auto rounded-xl border border-border p-3 bg-muted/30">
                {findings.map((finding, idx) => (
                  <div key={`${finding.field}-${idx}`} className="space-y-1 text-sm">
                    <div className="flex items-start gap-2">
                      <Badge
                        variant="outline"
                        className={cn('text-[10px] shrink-0 mt-0.5', severityClass(finding.severity))}
                      >
                        {severityLabel(finding.severity)}
                      </Badge>
                      <span className="text-foreground">{getMcpFindingDescription(finding, t)}</span>
                    </div>
                    {finding.recommendation ? (
                      <p className="text-xs text-muted-foreground pl-1">
                        {getMcpFindingRecommendation(finding, t)}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>{t('mcpCancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-orange-600 hover:bg-orange-700 text-white"
          >
            {t('mcpScanAckConfirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

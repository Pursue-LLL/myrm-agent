'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import type { BatchRiskReport } from '@/lib/approval/batchRisk';

interface BatchHighRiskConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: BatchRiskReport | null;
  onConfirmAll: () => void;
  onApproveSafeOnly: () => void;
  isSubmitting?: boolean;
}

export function BatchHighRiskConfirmDialog({
  open,
  onOpenChange,
  report,
  onConfirmAll,
  onApproveSafeOnly,
  isSubmitting = false,
}: BatchHighRiskConfirmDialogProps) {
  const t = useTranslations('toolApproval.batchHighRisk');

  if (!report || !report.hasHighRisk) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 text-destructive mb-1">
            <ShieldAlert className="h-5 w-5" />
            <DialogTitle>{t('dialogTitle')}</DialogTitle>
          </div>
          <DialogDescription>
            {t('dialogDesc', {
              total: report.totalCount,
              highRiskCount: report.highRiskCount,
            })}
          </DialogDescription>
        </DialogHeader>

        <div className="my-2 max-h-48 overflow-y-auto space-y-2 rounded-md border p-2 bg-muted/40">
          {report.highRiskItems.map((item) => (
            <div
              key={item.itemId}
              className="flex items-start gap-2 text-xs rounded border border-destructive/20 bg-destructive/5 p-2"
            >
              <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
              <div className="flex flex-col flex-1 overflow-hidden">
                <span className="font-semibold text-foreground truncate">
                  {item.toolName || item.actionType}
                </span>
                <span className="text-muted-foreground break-words">{item.riskReason}</span>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter className="flex flex-col sm:flex-row gap-2 sm:justify-end">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            {t('cancel')}
          </Button>

          {report.safeCount > 0 && (
            <Button
              variant="secondary"
              onClick={onApproveSafeOnly}
              disabled={isSubmitting}
            >
              {t('approveSafeOnly', { count: report.safeCount })}
            </Button>
          )}

          <Button
            variant="destructive"
            onClick={onConfirmAll}
            disabled={isSubmitting}
          >
            {t('confirmAll')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

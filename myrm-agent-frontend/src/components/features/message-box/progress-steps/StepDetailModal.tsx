'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Copy, Terminal, Activity, AlertCircle, Wrench, Clock, User } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { ProgressItem } from '@/store/chat/types';

interface StepDetailModalProps {
  step: ProgressItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function StepDetailModal({ step, open, onOpenChange }: StepDetailModalProps) {
  const t = useTranslations('progressSteps.detailModal');
  const [copied, setCopied] = useState(false);

  if (!step) {
    return null;
  }

  const handleCopyRaw = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(step, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard write failure fallback
    }
  };

  const durationText =
    step.duration_ms != null && step.duration_ms > 0
      ? step.duration_ms < 1000
        ? `${step.duration_ms}ms`
        : `${(step.duration_ms / 1000).toFixed(2)}s`
      : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-6 gap-4">
        <DialogHeader className="space-y-1">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            <DialogTitle className="text-lg font-semibold">{t('title')}</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            {t('subtitle')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 overflow-y-auto pr-1 text-sm">
          {/* Metadata badges */}
          <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-muted/40 border border-border/50">
            {step.tool_name && (
              <div className="flex items-center gap-2">
                <Wrench className="w-4 h-4 text-muted-foreground shrink-0" />
                <span className="text-xs text-muted-foreground">{t('toolName')}:</span>
                <span className="text-xs font-mono font-medium truncate">{step.tool_name}</span>
              </div>
            )}
            {(step.display_name || step.agent_instance) && (
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-muted-foreground shrink-0" />
                <span className="text-xs text-muted-foreground">{t('agentInstance')}:</span>
                <span className="text-xs font-medium truncate">{step.display_name || step.agent_instance}</span>
              </div>
            )}
            {durationText && (
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
                <span className="text-xs text-muted-foreground">{t('duration')}:</span>
                <span className="text-xs font-mono">{durationText}</span>
              </div>
            )}
            {step.status && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{t('status')}:</span>
                <Badge
                  variant={step.status === 'error' ? 'destructive' : 'secondary'}
                  className="text-[11px] font-mono capitalize"
                >
                  {step.status}
                </Badge>
              </div>
            )}
          </div>

          {/* Reason / intent */}
          {step.reason && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">{t('reason')}</span>
              <div className="p-3 rounded-lg bg-muted/30 border border-border/40 text-xs text-foreground/90 leading-relaxed whitespace-pre-wrap">
                {step.reason}
              </div>
            </div>
          )}

          {/* Diagnostic or Error */}
          {(step.error_hint || typeof step.error === 'string') && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-destructive flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5" />
                {t('diagnostic')}
              </span>
              <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-xs text-destructive leading-relaxed whitespace-pre-wrap">
                {step.error_hint || String(step.error)}
              </div>
            </div>
          )}

          {/* Payload items */}
          {step.items && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">{t('payload')}</span>
              <pre className="p-3 rounded-lg bg-muted/50 border border-border/40 text-xs font-mono overflow-x-auto max-h-48 text-foreground/90">
                {typeof step.items === 'string' ? step.items : JSON.stringify(step.items, null, 2)}
              </pre>
            </div>
          )}

          {/* Stdout */}
          {step.stdout && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5" />
                {t('stdout')}
              </span>
              <pre className="p-3 rounded-lg bg-black/90 text-green-400 font-mono text-xs overflow-x-auto max-h-48 whitespace-pre-wrap">
                {step.stdout}
              </pre>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between pt-2 border-t border-border/40 mt-auto">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleCopyRaw}
            className="text-xs gap-1.5"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? t('copied') : t('copyRaw')}
          </Button>
          <Button
            type="button"
            variant="default"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs"
          >
            {t('close')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

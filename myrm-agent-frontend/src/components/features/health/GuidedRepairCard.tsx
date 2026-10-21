'use client';
/**
 * [INPUT]
 * - src/services/runtime-health.ts::executeRepairAction (POS: 执行修复操作的 API 客户端)
 *
 * [OUTPUT]
 * - GuidedRepairCard: 交互式系统自动修复卡片。
 *
 * [POS]
 * 引导式修复卡片组件。向用户透明化修复操作的边界、预期效果与安全限制，提供执行修复的界面。
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { executeRepairAction, type RepairAction, type RepairActionExecuteResult } from '@/services/runtime-health';

const AlertTriangleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
const CheckCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);
const InfoIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);
const LoaderIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </svg>
);
const ShieldCheckIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <polyline points="9 12 11 14 15 10" />
  </svg>
);
const WrenchIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

interface GuidedRepairCardProps {
  action: RepairAction;
  onExecuted?: () => void;
}

const riskStyle: Record<RepairAction['risk_level'], string> = {
  low: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  medium: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  high: 'bg-red-500/10 text-red-600 dark:text-red-400',
};

export function GuidedRepairCard({ action, onExecuted }: GuidedRepairCardProps) {
  const t = useTranslations('settings.systemHealth.repair');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RepairActionExecuteResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAction = async (dryRun: boolean) => {
    if (!action.executable) {
      return;
    }

    setRunning(true);
    setError(null);
    try {
      const response = await executeRepairAction(action.action_id, {
        dry_run: dryRun,
        confirm: !dryRun,
      });
      setResult(response);
      if (!dryRun && response.changed) {
        onExecuted?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('executeFailed'));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card className="bg-muted/30">
      <CardHeader className="space-y-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              {action.executable ? (
                <WrenchIcon className="h-4 w-4 text-primary" />
              ) : (
                <InfoIcon className="h-4 w-4 text-muted-foreground" />
              )}
              {action.title}
            </CardTitle>
            <CardDescription>{action.description}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className={cn('text-xs', riskStyle[action.risk_level])}>{t(`risk.${action.risk_level}`)}</Badge>
            <Badge variant="outline" className="text-muted-foreground">
              {action.scope.replaceAll('_', ' ')}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded-lg border border-border/60 bg-muted/50 p-3">
            <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
              <AlertTriangleIcon className="h-4 w-4 text-amber-700 dark:text-amber-400" />
              {t('whyAppears')}
            </div>
            <p className="text-muted-foreground">{action.reason}</p>
          </div>
          <div className="rounded-lg border border-border/60 bg-muted/50 p-3">
            <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
              <ShieldCheckIcon className="h-4 w-4 text-emerald-700 dark:text-emerald-400" />
              {t('expectedEffect')}
            </div>
            <p className="text-muted-foreground">{action.expected_effect}</p>
          </div>
        </div>

        {action.does_not_do.length > 0 && (
          <div className="rounded-lg border border-border/60 bg-muted/40 p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('safetyBoundary')}
            </p>
            <ul className="space-y-1 text-sm text-muted-foreground">
              {action.does_not_do.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-muted-foreground/60">-</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {result && (
          <div className="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/50 p-3 text-sm text-foreground/80">
            <CheckCircleIcon className="mt-0.5 h-4 w-4 text-emerald-700 dark:text-emerald-400" />
            <span>{result.message}</span>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {action.executable ? (
            <>
              {action.dry_run_supported && (
                <Button variant="outline" size="sm" disabled={running} onClick={() => runAction(true)}>
                  {running ? <LoaderIcon className="mr-2 h-4 w-4 animate-spin" /> : null}
                  {t('preview')}
                </Button>
              )}
              <Button size="sm" disabled={running} onClick={() => runAction(false)}>
                {running ? (
                  <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <WrenchIcon className="mr-2 h-4 w-4" />
                )}
                {t('confirmRepair')}
              </Button>
            </>
          ) : (
            <Badge variant="outline" className="text-muted-foreground">
              {t('advisoryOnly')}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

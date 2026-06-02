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

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
  low: 'bg-emerald-500/10 text-emerald-500',
  medium: 'bg-yellow-500/10 text-yellow-500',
  high: 'bg-red-500/10 text-red-500',
};

export function GuidedRepairCard({ action, onExecuted }: GuidedRepairCardProps) {
  const t = useTranslations('settings.systemHealth.repair');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RepairActionExecuteResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAction = async (dryRun: boolean) => {
    if (!action.executable) return;

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
    <Card className="border-zinc-800 bg-zinc-900/80">
      <CardHeader className="space-y-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              {action.executable ? (
                <WrenchIcon className="h-4 w-4 text-indigo-400" />
              ) : (
                <InfoIcon className="h-4 w-4 text-zinc-400" />
              )}
              {action.title}
            </CardTitle>
            <CardDescription className="text-zinc-400">{action.description}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className={cn('text-xs', riskStyle[action.risk_level])}>{t(`risk.${action.risk_level}`)}</Badge>
            <Badge variant="outline" className="border-zinc-700 text-zinc-300">
              {action.scope.replaceAll('_', ' ')}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="mb-1 flex items-center gap-2 font-medium text-zinc-200">
              <AlertTriangleIcon className="h-4 w-4 text-yellow-500" />
              {t('whyAppears')}
            </div>
            <p className="text-zinc-400">{action.reason}</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="mb-1 flex items-center gap-2 font-medium text-zinc-200">
              <ShieldCheckIcon className="h-4 w-4 text-emerald-500" />
              {t('expectedEffect')}
            </div>
            <p className="text-zinc-400">{action.expected_effect}</p>
          </div>
        </div>

        {action.does_not_do.length > 0 && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">{t('safetyBoundary')}</p>
            <ul className="space-y-1 text-sm text-zinc-400">
              {action.does_not_do.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-zinc-600">-</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {result && (
          <div className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 text-sm text-zinc-300">
            <CheckCircleIcon className="mt-0.5 h-4 w-4 text-emerald-500" />
            <span>{result.message}</span>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>
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
            <Badge variant="outline" className="border-zinc-700 text-zinc-400">
              {t('advisoryOnly')}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

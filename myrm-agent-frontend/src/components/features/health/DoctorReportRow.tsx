/**
 * [INPUT]
 * - services/runtime-health.ts::HealthReport, HealthStatus (POS: 运行时健康API类型)
 * - components/features/health/doctor-icons.tsx::* (POS: 诊断面板SVG图标)
 * - lib/desktop/permissionDeepLink.ts::openPermissionDeepLinkWithGuideFallback, pickSettingsDeepLinkFromMeta (POS: 系统设置深链)
 *
 * [OUTPUT]
 * - STATUS_TEXT_CLASS: 状态文字色（亮/暗主题成对）
 * - DoctorReportRow: 单条体检结果行（已本地化的标题 / 摘要 / 状态，技术详情按需展开）
 *
 * [POS]
 * DoctorDashboard 的行级展示组件：只负责排版与主题色，文案由调用方按 doctorReportView 的描述解析后传入。
 */

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { HealthReport, HealthStatus } from '@/services/runtime-health';
import { AlertCircleIcon, CheckCircleIcon, XCircleIcon } from './doctor-icons';
import {
  openPermissionDeepLinkWithGuideFallback,
  pickSettingsDeepLinkFromMeta,
} from '@/lib/desktop/permissionDeepLink';

// Light/dark pairs keep status text at WCAG AA contrast on both card backgrounds.
export const STATUS_TEXT_CLASS: Record<HealthStatus, string> = {
  pass: 'text-emerald-700 dark:text-emerald-400',
  warn: 'text-amber-700 dark:text-amber-400',
  fail: 'text-red-600 dark:text-red-400',
};

const STATUS_BADGE_CLASS: Record<HealthStatus, string> = {
  pass: 'bg-emerald-500/10 hover:bg-emerald-500/20',
  warn: 'bg-amber-500/10 hover:bg-amber-500/20',
  fail: 'bg-red-500/10 hover:bg-red-500/20',
};

const STATUS_BADGE_VARIANT = { pass: 'default', warn: 'secondary', fail: 'destructive' } as const;

const STATUS_ICON = { pass: CheckCircleIcon, warn: AlertCircleIcon, fail: XCircleIcon } as const;

interface DoctorReportRowProps {
  report: HealthReport;
  title: string;
  summary: string;
  statusLabel: string;
  openSettingsLabel: string;
  technicalOpen: boolean;
  technical: { label: string; value: string }[];
}

export function DoctorReportRow({
  report,
  title,
  summary,
  statusLabel,
  openSettingsLabel,
  technicalOpen,
  technical,
}: DoctorReportRowProps) {
  const StatusIcon = STATUS_ICON[report.status];
  const settingsLink =
    report.component_name === 'DesktopControl' && report.status === 'warn'
      ? pickSettingsDeepLinkFromMeta(report.meta_data ?? undefined)
      : null;

  const openSettings = () => {
    if (!settingsLink) {
      return;
    }
    const platform =
      report.meta_data && typeof report.meta_data.platform === 'string' ? report.meta_data.platform : null;
    openPermissionDeepLinkWithGuideFallback(settingsLink, platform);
  };

  return (
    <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <StatusIcon className={cn('mt-0.5 h-4 w-4 shrink-0', STATUS_TEXT_CLASS[report.status])} />
          <div className="min-w-0 space-y-0.5">
            <h4 className="break-words text-sm font-medium">{title}</h4>
            <p className="break-words text-xs text-muted-foreground">{summary}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-1.5 sm:items-end">
          <Badge
            variant={STATUS_BADGE_VARIANT[report.status]}
            className={cn('text-xs', STATUS_BADGE_CLASS[report.status], STATUS_TEXT_CLASS[report.status])}
          >
            {statusLabel}
          </Badge>
          {settingsLink && (
            <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={openSettings}>
              {openSettingsLabel}
            </Button>
          )}
        </div>
      </div>
      {technicalOpen && technical.length > 0 && (
        <dl className="mt-2 space-y-1 rounded-md bg-muted/50 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {technical.map(({ label, value }) => (
            <div key={label} className="break-words">
              <dt className="inline font-semibold">{label}: </dt>
              <dd className="inline">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

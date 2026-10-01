'use client';

/**
 * [INPUT]
 * - @/lib/desktop/permissionDeepLink (POS: 桌面权限引导深链 SSOT)
 *
 * [OUTPUT]
 * - PermissionRow: OS 权限基础开关行
 * - CaptureProbeRow: 屏幕捕获探针验证行
 * - ScreenLockRow: 物理锁屏与休眠硬阻断安全门禁状态行
 * - DeeplinkItem: 深度跳转及命令复制辅助条
 *
 * [POS]
 * DesktopPermissionsCard 的拆分子组件视图行，纯展示组件。
 */

import { memo } from 'react';
import { ExternalLink, Copy } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { isSystemSettingsDeepLink } from '@/lib/desktop/permissionDeepLink';

export const PermissionRow = memo<{
  label: string;
  description: string;
  granted: boolean;
  isLoading: boolean;
  statusOkLabel: string;
  statusMissingLabel: string;
}>(({ label, description, granted, isLoading, statusOkLabel, statusMissingLabel }) => (
  <div className="px-5 py-4 flex items-center justify-between">
    <div className="flex items-center gap-3 flex-1 min-w-0">
      <div
        className={cn(
          'w-2 h-2 rounded-full',
          isLoading ? 'bg-muted-foreground animate-pulse' : granted ? 'bg-emerald-500' : 'bg-rose-500',
        )}
      />
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
    <span
      className={cn(
        'text-xs font-medium px-2.5 py-1 rounded-full',
        isLoading
          ? 'bg-muted text-muted-foreground'
          : granted
            ? 'bg-emerald-500/10 text-emerald-500'
            : 'bg-rose-500/10 text-rose-500',
      )}
    >
      {isLoading ? '...' : granted ? statusOkLabel : statusMissingLabel}
    </span>
  </div>
));

PermissionRow.displayName = 'PermissionRow';

export const CaptureProbeRow = memo<{
  label: string;
  description: string;
  capturable: boolean | null;
  isLoading: boolean;
  statusOkLabel: string;
  statusUnverifiedLabel: string;
  statusMissingLabel: string;
}>(({ label, description, capturable, isLoading, statusOkLabel, statusUnverifiedLabel, statusMissingLabel }) => {
  const tone = isLoading ? 'loading' : capturable === true ? 'ok' : capturable === false ? 'missing' : 'unverified';
  const badge =
    tone === 'loading'
      ? '...'
      : tone === 'ok'
        ? statusOkLabel
        : tone === 'missing'
          ? statusMissingLabel
          : statusUnverifiedLabel;

  return (
    <div className="px-5 py-4 flex items-center justify-between">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div
          className={cn(
            'w-2 h-2 rounded-full',
            tone === 'loading' && 'bg-muted-foreground animate-pulse',
            tone === 'ok' && 'bg-emerald-500',
            tone === 'missing' && 'bg-rose-500',
            tone === 'unverified' && 'bg-sky-500',
          )}
        />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <span
        className={cn(
          'text-xs font-medium px-2.5 py-1 rounded-full',
          tone === 'loading' && 'bg-muted text-muted-foreground',
          tone === 'ok' && 'bg-emerald-500/10 text-emerald-500',
          tone === 'missing' && 'bg-rose-500/10 text-rose-500',
          tone === 'unverified' && 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
        )}
      >
        {badge}
      </span>
    </div>
  );
});

CaptureProbeRow.displayName = 'CaptureProbeRow';

export const ScreenLockRow = memo<{
  label: string;
  description: string;
  isLocked: boolean;
  isLoading: boolean;
}>(({ label, description, isLocked, isLoading }) => (
  <div className="px-5 py-4 flex items-center justify-between">
    <div className="flex items-center gap-3 flex-1 min-w-0">
      <div
        className={cn(
          'w-2 h-2 rounded-full',
          isLoading ? 'bg-muted-foreground animate-pulse' : isLocked ? 'bg-amber-500' : 'bg-emerald-500',
        )}
      />
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
    <span
      className={cn(
        'text-xs font-medium px-2.5 py-1 rounded-full',
        isLoading
          ? 'bg-muted text-muted-foreground'
          : isLocked
            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            : 'bg-emerald-500/10 text-emerald-500',
      )}
    >
      {isLoading ? '...' : isLocked ? 'Locked (Blocked)' : 'Unlocked (Active)'}
    </span>
  </div>
));

ScreenLockRow.displayName = 'ScreenLockRow';

export const DeeplinkItem = memo<{
  label: string;
  value: string;
  onCopy: (value: string) => void;
  onOpen: (url: string) => void;
  openSettingsTitle: string;
  copyCommandTitle: string;
}>(({ label, value, onCopy, onOpen, openSettingsTitle, copyCommandTitle }) => {
  const isSystemLink = isSystemSettingsDeepLink(value);
  const isCommand = !isSystemLink;

  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 border border-border/20">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-foreground capitalize">{label.replace(/_/g, ' ')}</p>
        <p className="text-xs text-muted-foreground font-mono truncate">{value}</p>
      </div>
      {isCommand ? (
        <button
          onClick={() => onCopy(value)}
          className="p-1.5 rounded-lg hover:bg-muted/50 transition-colors flex-shrink-0"
          title={copyCommandTitle}
        >
          <Copy className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      ) : (
        <button
          onClick={() => onOpen(value)}
          className="p-1.5 rounded-lg hover:bg-muted/50 transition-colors flex-shrink-0"
          title={openSettingsTitle}
        >
          <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      )}
    </div>
  );
});

DeeplinkItem.displayName = 'DeeplinkItem';

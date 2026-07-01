'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端统一请求入口)
 * - @/lib/utils/toast::toast (POS: 全局 toast 通知)
 * - @/lib/deploy-mode::isLocalMode (POS: 前端部署模式判定)
 *
 * [OUTPUT]
 * - DesktopPermissionsCard: 桌面自动化就绪检测卡片，展示 OS 权限/依赖状态及修复提示
 *
 * [POS]
 * 系统设置中的环境诊断卡片。仅本地/Tauri模式渲染，调用 GET /webui/desktop/permissions 实时检测输入控制和屏幕捕获能力就绪状态。
 */

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { MonitorCheck, CheckCircle2, XCircle, ExternalLink, RefreshCw, Copy } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import { isLocalMode } from '@/lib/deploy-mode';

interface DesktopPermissionsStatus {
  accessibility: boolean;
  screen_recording: boolean;
  all_granted: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
}

const DesktopPermissionsCard = memo(() => {
  const t = useTranslations('settings.desktopPermissions');
  const [status, setStatus] = useState<DesktopPermissionsStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  if (!isLocalMode()) return null;

  const fetchPermissions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiRequest<DesktopPermissionsStatus>(
        '/webui/desktop/permissions',
        { silent: true },
      );
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to check permissions');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPermissions();
  }, [fetchPermissions]);

  const handleCopyCommand = useCallback((command: string) => {
    void navigator.clipboard.writeText(command);
    toast.success(t('copiedToClipboard'));
  }, [t]);

  const handleOpenDeeplink = useCallback((url: string) => {
    if (url.startsWith('x-apple.systempreferences:') || url.startsWith('ms-settings:')) {
      window.open(url, '_blank');
    }
  }, []);

  if (error) {
    return (
      <section className="space-y-6">
        <div className="flex items-center gap-3 px-2">
          <MonitorCheck className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
            {t('title')}
          </h2>
        </div>
        <div className="rounded-2xl border border-border/40 bg-card/50 backdrop-blur-sm p-5">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{t('checkFailed')}</p>
            <button
              onClick={() => void fetchPermissions()}
              className="p-2 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <RefreshCw className="w-4 h-4 text-muted-foreground" />
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <MonitorCheck className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
          {t('title')}
        </h2>
      </div>

      <div className="rounded-2xl border border-border/40 bg-card/50 backdrop-blur-sm overflow-hidden divide-y divide-border/20">
        {/* Header with overall status */}
        <div className="p-5 flex items-center justify-between">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {!status ? (
              <div className="p-2 rounded-lg bg-muted/50">
                <RefreshCw className="w-4 h-4 text-muted-foreground animate-spin" />
              </div>
            ) : status.all_granted ? (
              <div className="p-2 rounded-lg bg-emerald-500/10">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              </div>
            ) : (
              <div className="p-2 rounded-lg bg-amber-500/10">
                <XCircle className="w-4 h-4 text-amber-500" />
              </div>
            )}
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">
                {!status ? t('checking') : status.all_granted ? t('allReady') : t('actionRequired')}
              </p>
              <p className="text-xs text-muted-foreground">
                {status ? t('platform', { name: status.platform }) : ''}
              </p>
            </div>
          </div>
          <button
            onClick={() => void fetchPermissions()}
            disabled={isLoading}
            className="p-2 rounded-lg hover:bg-muted/50 transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4 text-muted-foreground', isLoading && 'animate-spin')} />
          </button>
        </div>

        {/* Accessibility check */}
        <PermissionRow
          label={t('accessibility')}
          description={t('accessibilityDesc')}
          granted={status?.accessibility ?? false}
          isLoading={isLoading}
        />

        {/* Screen recording check */}
        <PermissionRow
          label={t('screenRecording')}
          description={t('screenRecordingDesc')}
          granted={status?.screen_recording ?? false}
          isLoading={isLoading}
        />

        {/* Deeplinks / repair hints */}
        {status && !status.all_granted && Object.keys(status.settings_deeplinks).length > 0 && (
          <div className="p-5 space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {t('fixHints')}
            </p>
            {Object.entries(status.settings_deeplinks).map(([key, value]) => (
              <DeeplinkItem
                key={key}
                label={key}
                value={value}
                onCopy={handleCopyCommand}
                onOpen={handleOpenDeeplink}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
});

DesktopPermissionsCard.displayName = 'DesktopPermissionsCard';

export default DesktopPermissionsCard;

// ============================================================================
// Sub-components
// ============================================================================

const PermissionRow = memo<{
  label: string;
  description: string;
  granted: boolean;
  isLoading: boolean;
}>(({ label, description, granted, isLoading }) => (
  <div className="px-5 py-4 flex items-center justify-between">
    <div className="flex items-center gap-3 flex-1 min-w-0">
      <div className={cn(
        'w-2 h-2 rounded-full',
        isLoading ? 'bg-muted-foreground animate-pulse' : granted ? 'bg-emerald-500' : 'bg-rose-500',
      )} />
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
    <span className={cn(
      'text-xs font-medium px-2.5 py-1 rounded-full',
      isLoading
        ? 'bg-muted text-muted-foreground'
        : granted
          ? 'bg-emerald-500/10 text-emerald-500'
          : 'bg-rose-500/10 text-rose-500',
    )}>
      {isLoading ? '...' : granted ? 'OK' : 'Missing'}
    </span>
  </div>
));

PermissionRow.displayName = 'PermissionRow';

const DeeplinkItem = memo<{
  label: string;
  value: string;
  onCopy: (value: string) => void;
  onOpen: (url: string) => void;
}>(({ label, value, onCopy, onOpen }) => {
  const isSystemLink = value.startsWith('x-apple.systempreferences:') || value.startsWith('ms-settings:');
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
          title="Copy command"
        >
          <Copy className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      ) : (
        <button
          onClick={() => onOpen(value)}
          className="p-1.5 rounded-lg hover:bg-muted/50 transition-colors flex-shrink-0"
          title="Open settings"
        >
          <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      )}
    </div>
  );
});

DeeplinkItem.displayName = 'DeeplinkItem';

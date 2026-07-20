'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端统一请求入口)
 * - @/lib/utils/toast::toast (POS: 全局 toast 通知)
 * - @/lib/deploy-mode::isLocalMode (POS: 前端部署模式判定)
 *
 * [OUTPUT]
 * - DesktopPermissionsCard: 桌面自动化就绪检测卡片；OS 权限状态 + 始终信任应用列表（含加载失败重试）
 *
 * [POS]
 * 系统设置中的环境诊断卡片。仅本地/Tauri 模式渲染；`GET /webui/desktop/permissions` + `GET/DELETE /webui/desktop/trust/apps`。
 */

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { MonitorCheck, CheckCircle2, XCircle, ExternalLink, RefreshCw, Copy } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import { isLocalMode } from '@/lib/deploy-mode';
import { isSystemSettingsDeepLink, openPermissionDeepLink } from '@/lib/desktop/permissionDeepLink';

interface DesktopPermissionsStatus {
  accessibility: boolean;
  screen_recording: boolean;
  all_granted: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
}

interface TrustedDesktopApp {
  trust_key: string;
  display_name: string;
  app_id: string;
  scope: string;
}

const DesktopPermissionsCardLocal = memo(() => {
  const t = useTranslations('settings.desktopPermissions');
  const [status, setStatus] = useState<DesktopPermissionsStatus | null>(null);
  const [trustedApps, setTrustedApps] = useState<TrustedDesktopApp[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isTrustLoading, setIsTrustLoading] = useState(true);
  const [revokingKey, setRevokingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trustError, setTrustError] = useState<string | null>(null);

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

  const fetchTrustedApps = useCallback(async () => {
    setIsTrustLoading(true);
    setTrustError(null);
    try {
      const data = await apiRequest<{ apps: TrustedDesktopApp[] }>(
        '/webui/desktop/trust/apps',
        { silent: true },
      );
      setTrustedApps(Array.isArray(data.apps) ? data.apps : []);
    } catch (err) {
      setTrustError(err instanceof Error ? err.message : t('trustedAppsLoadFailed'));
    } finally {
      setIsTrustLoading(false);
    }
    // `t` from next-intl is stable in production; omit from deps to avoid refetch loops.
  }, []);

  useEffect(() => {
    void fetchPermissions();
    void fetchTrustedApps();
  }, [fetchPermissions, fetchTrustedApps]);

  const handleRevokeTrustedApp = useCallback(async (trustKey: string) => {
    if (revokingKey) return;
    setRevokingKey(trustKey);
    try {
      await apiRequest('/webui/desktop/trust/apps', {
        method: 'DELETE',
        body: JSON.stringify({ trust_key: trustKey }),
      });
      setTrustedApps((prev) => prev.filter((app) => app.trust_key !== trustKey));
      toast.success(t('trustedAppsRevokeSuccess'));
    } catch {
      toast.error(t('trustedAppsRevokeFailed'));
    } finally {
      setRevokingKey(null);
    }
  }, [revokingKey, t]);

  const handleCopyCommand = useCallback((command: string) => {
    void navigator.clipboard.writeText(command);
    toast.success(t('copiedToClipboard'));
  }, [t]);

  const handleOpenDeeplink = useCallback((url: string) => {
    openPermissionDeepLink(url);
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
          statusOkLabel={t('statusOk')}
          statusMissingLabel={t('statusMissing')}
        />

        {/* Screen recording check */}
        <PermissionRow
          label={t('screenRecording')}
          description={t('screenRecordingDesc')}
          granted={status?.screen_recording ?? false}
          isLoading={isLoading}
          statusOkLabel={t('statusOk')}
          statusMissingLabel={t('statusMissing')}
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
                openSettingsTitle={t('openSettings')}
                copyCommandTitle={t('copyCommand')}
              />
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-border/40 bg-card/50 backdrop-blur-sm overflow-hidden">
        <div className="p-5 space-y-1">
          <p className="text-sm font-semibold text-foreground">{t('trustedAppsTitle')}</p>
          <p className="text-xs text-muted-foreground">{t('trustedAppsDesc')}</p>
        </div>
        <div className="divide-y divide-border/20">
          {isTrustLoading ? (
            <div className="px-5 py-4 flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              {t('checking')}
            </div>
          ) : trustError ? (
            <div className="px-5 py-4 flex items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">{t('trustedAppsLoadFailed')}</p>
              <button
                type="button"
                onClick={() => void fetchTrustedApps()}
                className="p-2 rounded-lg hover:bg-muted/50 transition-colors shrink-0"
                title={t('trustedAppsRetry')}
              >
                <RefreshCw className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
          ) : trustedApps.length === 0 ? (
            <div className="px-5 py-4 text-sm text-muted-foreground">{t('trustedAppsEmpty')}</div>
          ) : (
            trustedApps.map((app) => (
              <div key={app.trust_key} className="px-5 py-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{app.display_name}</p>
                  {app.app_id ? (
                    <p className="text-xs text-muted-foreground font-mono truncate">{app.app_id}</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  disabled={revokingKey === app.trust_key}
                  onClick={() => void handleRevokeTrustedApp(app.trust_key)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted/50 transition-colors disabled:opacity-50 shrink-0"
                >
                  {t('trustedAppsRevoke')}
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
});

DesktopPermissionsCardLocal.displayName = 'DesktopPermissionsCardLocal';

const DesktopPermissionsCard = memo(() => {
  if (!isLocalMode()) return null;
  return <DesktopPermissionsCardLocal />;
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
  statusOkLabel: string;
  statusMissingLabel: string;
}>(({ label, description, granted, isLoading, statusOkLabel, statusMissingLabel }) => (
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
      {isLoading ? '...' : granted ? statusOkLabel : statusMissingLabel}
    </span>
  </div>
));

PermissionRow.displayName = 'PermissionRow';

const DeeplinkItem = memo<{
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

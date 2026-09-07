'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端统一请求入口)
 * - @/lib/desktop/permissionDeepLink (POS: 桌面权限引导深链 SSOT)
 *
 * [OUTPUT]
 * - CuPermissionInline: Agent 配置面板内 computer_use 权限探测条
 *   （verified / grants-ok-unverified / missing / error）
 *
 * [POS]
 * BuiltinToolsPanel 子组件。本地模式启用 computer_use 时展示 OS 权限状态与设置入口。
 */

import { useState, useEffect, useCallback } from 'react';
import { Loader2, CheckCircle2, AlertTriangle, RefreshCw, ExternalLink, CircleDashed } from 'lucide-react';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils/classnameUtils';
import { openPermissionDeepLinkWithGuideFallback, pickSettingsDeepLink } from '@/lib/desktop/permissionDeepLink';

interface CuPermissionsResponse {
  accessibility: boolean;
  screen_recording: boolean;
  screen_recording_capturable: boolean | null;
  all_granted: boolean;
  capture_ready: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
}

type InlineTone = 'verified' | 'unverified' | 'missing';

export const CuPermissionInline = ({ tPanel }: { tPanel: (key: string) => string }) => {
  const [status, setStatus] = useState<CuPermissionsResponse | null>(null);
  // Start true to avoid a one-frame amber "missing" flash before the first probe.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const check = useCallback(async (probeCapture = false) => {
    setLoading(true);
    setError(false);
    try {
      const path = probeCapture
        ? '/webui/desktop/permissions?probe_capture=true'
        : '/webui/desktop/permissions';
      const data = await apiRequest<CuPermissionsResponse>(path, { silent: true });
      setStatus(data);
    } catch {
      setError(true);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (error) {
    return (
      <div className="p-3 rounded-xl border text-xs space-y-2 bg-amber-500/5 border-amber-500/20 text-amber-700 dark:text-amber-400">
        <div className="flex items-center gap-2 font-medium">
          <AlertTriangle size={14} />
          <span>{tPanel('cuPermission.checkFailed')}</span>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
          onClick={() => check(true)}
          disabled={loading}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {tPanel('cuPermission.recheckBtn')}
        </button>
      </div>
    );
  }

  const grantsOk = status?.all_granted === true;
  const capturable = status?.screen_recording_capturable;
  const verifiedReady = status?.capture_ready === true;
  const tone: InlineTone = verifiedReady
    ? 'verified'
    : grantsOk && capturable == null
      ? 'unverified'
      : 'missing';

  // Neutral shell while probing — never reuse "missing" amber for checking copy.
  const toneClass = loading
    ? 'bg-muted/40 border-border text-muted-foreground'
    : tone === 'verified'
      ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
      : tone === 'unverified'
        ? 'bg-sky-500/5 border-sky-500/20 text-sky-800 dark:text-sky-300'
        : 'bg-amber-500/5 border-amber-500/20 text-amber-700 dark:text-amber-400';

  const actionBtnClass =
    tone === 'verified'
      ? 'bg-emerald-500/15 hover:bg-emerald-500/25'
      : tone === 'unverified'
        ? 'bg-sky-500/15 hover:bg-sky-500/25'
        : 'bg-amber-500/15 hover:bg-amber-500/25';

  return (
    <div className={cn('p-3 rounded-xl border text-xs space-y-1.5', toneClass)}>
      {loading ? (
        <div className="flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" />
          <span>{tPanel('cuPermission.checking')}</span>
        </div>
      ) : tone === 'verified' ? (
        <div className="flex items-center gap-2">
          <CheckCircle2 size={14} />
          <span>{tPanel('cuPermission.allGranted')}</span>
        </div>
      ) : tone === 'unverified' ? (
        <>
          <div className="flex items-center gap-2 font-medium">
            <CircleDashed size={14} />
            <span>{tPanel('cuPermission.grantsOkCaptureUnverified')}</span>
          </div>
          <p className="text-[10px] opacity-75">{tPanel('cuPermission.captureUnverifiedHint')}</p>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              className={cn(
                'inline-flex items-center gap-1 px-2 py-1 rounded-md font-medium transition-colors',
                actionBtnClass,
              )}
              onClick={() => check(true)}
              disabled={loading}
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              {tPanel('cuPermission.recheckBtn')}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle size={14} />
            <span>{tPanel('cuPermission.missing')}</span>
          </div>
          <ul className="ml-5 list-disc space-y-0.5">
            {status && !status.accessibility && <li>{tPanel('cuPermission.accessibilityMissing')}</li>}
            {status && !status.screen_recording && <li>{tPanel('cuPermission.screenRecordingMissing')}</li>}
            {status && status.screen_recording && status.screen_recording_capturable === false && (
              <li>{tPanel('cuPermission.captureNotReady')}</li>
            )}
          </ul>
          <p className="text-[10px] opacity-75">{tPanel('cuPermission.hint')}</p>
          <div className="flex items-center gap-2 pt-1">
            {pickSettingsDeepLink(status?.settings_deeplinks) && (
              <button
                type="button"
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-1 rounded-md font-medium transition-colors',
                  actionBtnClass,
                )}
                onClick={() => {
                  const link = pickSettingsDeepLink(status?.settings_deeplinks);
                  if (link) {
                    openPermissionDeepLinkWithGuideFallback(link, status?.platform);
                  }
                }}
              >
                <ExternalLink size={12} />
                {tPanel('cuPermission.openSettings')}
              </button>
            )}
            <button
              type="button"
              className={cn(
                'inline-flex items-center gap-1 px-2 py-1 rounded-md font-medium transition-colors',
                actionBtnClass,
              )}
              onClick={() => check(true)}
              disabled={loading}
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              {tPanel('cuPermission.recheckBtn')}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

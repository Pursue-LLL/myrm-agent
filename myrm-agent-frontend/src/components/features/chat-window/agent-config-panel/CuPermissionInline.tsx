'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端统一请求入口)
 * - @/lib/desktop/permissionDeepLink (POS: 桌面权限引导深链 SSOT)
 *
 * [OUTPUT]
 * - CuPermissionInline: Agent 配置面板内 computer_use 权限探测条（ granted / missing / error ）
 *
 * [POS]
 * BuiltinToolsPanel 子组件。本地模式启用 computer_use 时展示 OS 权限状态与设置入口。
 */

'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端统一请求入口)
 * - @/lib/desktop/permissionDeepLink (POS: 桌面权限引导深链 SSOT)
 *
 * [OUTPUT]
 * - CuPermissionInline: Agent 配置面板内 computer_use 权限探测条（granted / missing / error）
 *
 * [POS]
 * BuiltinToolsPanel 子组件。本地模式启用 computer_use 时展示 OS 权限状态与设置入口。
 */

import { useState, useEffect, useCallback } from 'react';
import { Loader2, CheckCircle2, AlertTriangle, RefreshCw, ExternalLink } from 'lucide-react';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils/classnameUtils';
import {
  openPermissionDeepLinkWithGuideFallback,
  pickSettingsDeepLink,
} from '@/lib/desktop/permissionDeepLink';

interface CuPermissionsResponse {
  accessibility: boolean;
  screen_recording: boolean;
  all_granted: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
}

export const CuPermissionInline = ({ tPanel }: { tPanel: (key: string) => string }) => {
  const [status, setStatus] = useState<CuPermissionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const check = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await apiRequest<CuPermissionsResponse>('/webui/desktop/permissions', { silent: true });
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
          onClick={check}
          disabled={loading}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {tPanel('cuPermission.recheckBtn')}
        </button>
      </div>
    );
  }

  const allOk = status?.all_granted;

  return (
    <div
      className={cn(
        'p-3 rounded-xl border text-xs space-y-1.5',
        allOk
          ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
          : 'bg-amber-500/5 border-amber-500/20 text-amber-700 dark:text-amber-400',
      )}
    >
      {loading ? (
        <div className="flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" />
          <span>{tPanel('cuPermission.checking')}</span>
        </div>
      ) : allOk ? (
        <div className="flex items-center gap-2">
          <CheckCircle2 size={14} />
          <span>{tPanel('cuPermission.allGranted')}</span>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle size={14} />
            <span>{tPanel('cuPermission.missing')}</span>
          </div>
          <ul className="ml-5 list-disc space-y-0.5">
            {status && !status.accessibility && <li>{tPanel('cuPermission.accessibilityMissing')}</li>}
            {status && !status.screen_recording && <li>{tPanel('cuPermission.screenRecordingMissing')}</li>}
          </ul>
          <p className="text-[10px] opacity-75">{tPanel('cuPermission.hint')}</p>
          <div className="flex items-center gap-2 pt-1">
            {pickSettingsDeepLink(status?.settings_deeplinks) && (
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
                onClick={() => {
                  const link = pickSettingsDeepLink(status?.settings_deeplinks);
                  if (link) openPermissionDeepLinkWithGuideFallback(link);
                }}
              >
                <ExternalLink size={12} />
                {tPanel('cuPermission.openSettings')}
              </button>
            )}
            <button
              type="button"
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
              onClick={check}
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

'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, CheckCircle2, AlertTriangle, RefreshCw, ExternalLink } from 'lucide-react';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils/classnameUtils';

interface CuPermissionsResponse {
  accessibility: boolean;
  screen_recording: boolean;
  all_granted: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
}

function openPermissionDeepLink(url: string) {
  import('@tauri-apps/plugin-shell')
    .then((mod) => mod.open(url))
    .catch(() => {
      window.open(
        'https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac',
        '_blank',
      );
    });
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
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (error) return null;

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
            {status?.settings_deeplinks && Object.keys(status.settings_deeplinks).length > 0 && (
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
                onClick={() => {
                  const link = status.settings_deeplinks.accessibility || status.settings_deeplinks.screen_recording;
                  if (link) openPermissionDeepLink(link);
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

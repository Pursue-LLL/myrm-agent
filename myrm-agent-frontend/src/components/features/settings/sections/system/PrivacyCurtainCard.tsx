'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { EyeOff, MonitorX } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { useTauri } from '@/hooks/tauri/useTauri';
import Toggle from '@/components/features/settings/common/Toggle';
import { MYRM_PRIVACY_CURTAIN_SETTINGS_ANCHOR } from '@/lib/desktop/desktopSettingsAnchors';

interface PrivacyCurtainCardProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

/**
 * 工位防窥帷幕配置卡。
 *
 * 锁屏离开时每显示器自动全屏置顶黑幕：AI 经排除截图通道继续作业，
 * 物理路过者只见免扰看板；帷幕上任何交互立即回锁。手动拉起用于
 * 会议/离机场景，无人值守自动解锁需配合 Locked Use。
 */
const PrivacyCurtainCard = memo<PrivacyCurtainCardProps>(({ enabled, onToggle }) => {
  const t = useTranslations('settings.privacyCurtain');
  const { isTauri, invoke } = useTauri();
  const [isActive, setIsActive] = useState(false);
  const [platformSupport, setPlatformSupport] = useState<{
    curtain_supported: boolean;
    curtain_capture_excluded_on_desktop: boolean;
    curtain_capture_exclusion_ready: boolean;
    platform: string;
  } | null>(null);

  const refreshActive = useCallback(async () => {
    if (!isTauri || !invoke) {
      return;
    }
    try {
      const [active, support] = await Promise.all([
        invoke<boolean>('privacy_curtain_active'),
        invoke<{
          curtain_supported: boolean;
          curtain_capture_excluded_on_desktop: boolean;
          curtain_capture_exclusion_ready: boolean;
          platform: string;
        }>('screen_lock_platform_support'),
      ]);
      setIsActive(active);
      setPlatformSupport(support);
    } catch {
      // 状态回显失败不打断设置页
    }
  }, [isTauri, invoke]);

  useEffect(() => {
    void refreshActive();
  }, [refreshActive]);

  const curtainSupported = platformSupport?.curtain_supported === true;
  const captureExclusionReady = platformSupport?.curtain_capture_exclusion_ready === true;
  const curtainUsable = curtainSupported && captureExclusionReady;

  // 自动拉起/回锁收起由壳侧 watcher 触发，设置页开着时靠事件回显而不是只在挂载读一次。
  useEffect(() => {
    if (!isTauri) {
      return undefined;
    }
    let disposed = false;
    let unlisten: (() => void) | undefined;

    void import('@tauri-apps/api/event')
      .then(({ listen }) => listen('curtain:state-changed', () => void refreshActive()))
      .then((fn) => {
        if (disposed) {
          fn();
        } else {
          unlisten = fn;
        }
      })
      .catch((err) => {
        console.warn('[PrivacyCurtainCard] Failed to subscribe to curtain:state-changed:', err);
      });

    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [isTauri, refreshActive]);

  const handleEngage = useCallback(async () => {
    if (!invoke) {
      return;
    }
    try {
      await invoke('show_privacy_curtain');
      setIsActive(true);
      toast.success(t('toastEngaged'));
    } catch (err) {
      toast.error(t('toastFailed', { error: String(err) }));
    }
  }, [invoke, t]);

  const handleRelease = useCallback(async () => {
    if (!invoke) {
      return;
    }
    try {
      await invoke('hide_privacy_curtain');
      setIsActive(false);
      toast.success(t('toastReleased'));
    } catch (err) {
      toast.error(t('toastFailed', { error: String(err) }));
    }
  }, [invoke, t]);

  if (!isTauri) {
    return null;
  }

  return (
    <section id={MYRM_PRIVACY_CURTAIN_SETTINGS_ANCHOR} className="space-y-6 scroll-mt-24">
      <div className="flex items-center gap-3 px-2">
        <MonitorX className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="rounded-2xl border border-border/40 bg-card/50 backdrop-blur-sm overflow-hidden">
        <div className="p-5 space-y-4">
          {!curtainSupported && (
            <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2">
              {t('platformUnsupported', { platform: platformSupport?.platform ?? 'unknown' })}
            </p>
          )}
          {curtainSupported && !captureExclusionReady && (
            <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2">
              {t('captureExclusionUnavailable')}
            </p>
          )}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div className={cn('p-2 rounded-lg', enabled ? 'bg-indigo-500/10' : 'bg-muted/50')}>
                <EyeOff className={cn('w-4 h-4', enabled ? 'text-indigo-500' : 'text-muted-foreground')} />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{t('autoTitle')}</p>
                <p className="text-xs text-muted-foreground">{t('autoDesc')}</p>
              </div>
            </div>
            <Toggle
              checked={enabled}
              onChange={() => onToggle(!enabled)}
              disabled={!curtainUsable}
              ariaLabel={t('autoTitle')}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pl-12">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'text-xs font-medium px-2.5 py-1 rounded-full',
                  isActive ? 'bg-emerald-500/10 text-emerald-500' : 'bg-muted/50 text-muted-foreground',
                )}
              >
                {isActive ? t('activeBadge') : t('inactiveBadge')}
              </span>
            </div>
            <button
              disabled={!curtainUsable && !isActive}
              onClick={() => (isActive ? void handleRelease() : void handleEngage())}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
                !curtainUsable && !isActive
                  ? 'bg-muted/30 text-muted-foreground cursor-not-allowed'
                  : 'bg-muted/50 hover:bg-muted',
              )}
            >
              {isActive ? t('release') : t('engage')}
            </button>
          </div>

          <p className="pl-12 text-[10px] text-muted-foreground/60">{t('lockedUseHint')}</p>
        </div>
      </div>
    </section>
  );
});

PrivacyCurtainCard.displayName = 'PrivacyCurtainCard';

export default PrivacyCurtainCard;

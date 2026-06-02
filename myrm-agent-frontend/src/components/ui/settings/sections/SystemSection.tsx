'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconSettings,
  IconWifi,
  IconWifiOff,
  IconLock,
  IconStop,
  IconRefresh,
  IconCopy,
  IconCheck,
  IconExternalLink,
  IconGlobe,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import { SystemConfig, DEFAULT_SYSTEM_CONFIG } from '@/types/system';
import { useSystemConfig } from '@/hooks/useSystemConfig';
import { useDirtyGuard } from '@/hooks/useDirtyGuard';
import { useTunnel } from '@/hooks/useTunnel';
import useConfigStore from '@/store/useConfigStore';
import { systemService } from '@/services/system';
import IngressEntitlementGate from '@/components/billing/IngressEntitlementGate';
import BrowserPoolCard from './BrowserPoolCard';
import LockedUseCard from './LockedUseCard';
import MemoryMonitorCard from './MemoryMonitorCard';
import { DoctorDashboard } from '../../health/DoctorDashboard';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

/**
 * 系统设置 Section
 *
 * 功能：
 * - Desktop 模式：仅显示系统信息
 * - Tauri 模式：
 *   - 配置 WebUI 服务（启用/禁用、远程访问、密码）
 *   - 配置端口（Next.js 前端端口、FastAPI 后端端口）
 *   - 显示本地和远程访问地址
 *   - 提供重启应用功能
 */

// ============================================================================
// 子组件
// ============================================================================

const ShortcutRecorder = memo<{
  value: string;
  onChange: (value: string) => void;
}>(({ value, onChange }) => {
  const [isRecording, setIsRecording] = useState(false);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isRecording) return;
      e.preventDefault();
      e.stopPropagation();

      // Don't record if only modifiers are pressed
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        return;
      }

      // Escape to cancel recording
      if (e.key === 'Escape') {
        setIsRecording(false);
        return;
      }

      // Backspace to clear shortcut
      if (e.key === 'Backspace' || e.key === 'Delete') {
        onChange('');
        setIsRecording(false);
        return;
      }

      const keys: string[] = [];

      if (e.metaKey) keys.push('Super');
      if (e.ctrlKey) keys.push('Control');
      if (e.altKey) keys.push('Alt');
      if (e.shiftKey) keys.push('Shift');

      let mainKey = e.key.toUpperCase();
      if (e.code === 'Space') mainKey = 'Space';
      if (mainKey.length === 1 && mainKey >= 'A' && mainKey <= 'Z') {
        // ok
      } else if (mainKey >= '0' && mainKey <= '9') {
        // ok
      } else if (mainKey !== 'SPACE') {
        mainKey = e.code.replace('Key', '').replace('Digit', '');
      }

      keys.push(mainKey === 'SPACE' ? 'Space' : mainKey);

      onChange(keys.join('+'));
      setIsRecording(false);
    },
    [isRecording, onChange],
  );

  return (
    <input
      type="text"
      value={isRecording ? '录制中...' : value}
      onFocus={() => setIsRecording(true)}
      onBlur={() => setIsRecording(false)}
      onKeyDown={handleKeyDown}
      placeholder="e.g. Alt+Space"
      readOnly
      className={cn(
        'w-40 px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-center text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50 cursor-pointer transition-colors',
        isRecording && 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400',
      )}
    />
  );
});
ShortcutRecorder.displayName = 'ShortcutRecorder';

const ModeStatusBadge = memo<{ currentMode: 'desktop' | 'webui' }>(({ currentMode }) => {
  const t = useTranslations('settings.system');
  const isWebUI = currentMode === 'webui';

  return (
    <div
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest rounded-full border',
        isWebUI
          ? 'bg-indigo-500/10 text-indigo-500 border-indigo-500/20'
          : 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
      )}
    >
      <div className={cn('w-1.5 h-1.5 rounded-full', isWebUI ? 'bg-indigo-500' : 'bg-emerald-500')} />
      {isWebUI ? t('mode.webui') : t('mode.desktop')}
    </div>
  );
});
ModeStatusBadge.displayName = 'ModeStatusBadge';

function resolveWebuiPort(config: SystemConfig): number {
  if (isTauriRuntime()) {
    return config.webuiPort;
  }
  if (typeof window !== 'undefined' && window.location.port) {
    const parsed = Number.parseInt(window.location.port, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return config.webuiPort;
}

const AccessCard = memo<{
  config: SystemConfig;
  localIP: string;
}>(({ config, localIP }) => {
  const t = useTranslations('settings.system');
  const [copied, setCopied] = useState<string | null>(null);
  const [testingIngress, setTestingIngress] = useState(false);
  const publicIngressBaseUrl = useConfigStore((s) => s.publicIngressBaseUrl);
  const setPublicIngressBaseUrl = useConfigStore((s) => s.setPublicIngressBaseUrl);

  const accessEnabled = config.enableWebUIMode || (!isTauriRuntime() && isLocalMode());
  const webuiPort = resolveWebuiPort(config);
  const passwordProtectionEnabled = isTauriRuntime() ? config.requirePassword : true;
  const {
    status: tunnelStatus,
    starting: isTunnelStarting,
    start: startTunnel,
    stop: stopTunnel,
  } = useTunnel(webuiPort, passwordProtectionEnabled);
  const tunnelUrl = tunnelStatus.running ? tunnelStatus.url : null;
  const tunnelActive = Boolean(tunnelUrl);
  const showLocalIngress = isLocalMode();
  const [lanNetworkUrl, setLanNetworkUrl] = useState('');

  useEffect(() => {
    if (!showLocalIngress) {
      return;
    }
    let cancelled = false;
    void systemService.getLocalNetwork(webuiPort).then((data) => {
      if (!cancelled && data.url) {
        setLanNetworkUrl(data.url);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [showLocalIngress, webuiPort]);

  const localUrl = `http://localhost:${webuiPort}`;
  const remoteUrl = localIP
    ? `http://${localIP}:${webuiPort}`
    : lanNetworkUrl;

  const handleCopy = (text: string, type: string) => {
    writeToClipboard(text);
    setCopied(type);
    toast.success(t('copied'));
    setTimeout(() => setCopied(null), 2000);
  };

  const handleOpen = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleStartTunnel = async () => {
    if (!passwordProtectionEnabled) {
      toast.error(t('access.tunnel.passwordRequired'));
      if (isTauriRuntime()) {
        document.getElementById('require-password')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return;
    }
    try {
      await startTunnel();
      toast.success(t('access.tunnel.starting'));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.toLowerCase().includes('cloudflared')) {
        toast.error(t('access.tunnel.cloudflaredMissing'));
      } else {
        toast.error(message);
      }
    }
  };

  const lanQrSrc = remoteUrl
    ? localIP
      ? `/webui/qrcode.png?host=${localIP}&port=${webuiPort}`
      : `/webui/qrcode.png?url=${encodeURIComponent(remoteUrl)}`
    : '';

  const handleStopTunnel = async () => {
    try {
      await stopTunnel();
      toast.success(t('access.tunnel.stopped'));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      toast.error(message);
    }
  };

  const handleTestIngress = async () => {
    setTestingIngress(true);
    try {
      const ingressUrl = (await systemService.getIngressUrl()) || publicIngressBaseUrl;
      if (!ingressUrl) {
        toast.error(t('access.ingress.notConfigured'));
        return;
      }
      const ok = await systemService.testIngressHealth(ingressUrl);
      if (ok) {
        toast.success(t('access.ingress.testSuccess'));
      } else {
        toast.error(t('access.ingress.testFailed'));
      }
    } catch {
      toast.error(t('access.ingress.testFailed'));
    } finally {
      setTestingIngress(false);
    }
  };

  if (!accessEnabled) {
    return (
      <div className="p-6 rounded-2xl bg-white/5 border border-white/10 text-center text-muted-foreground">
        <IconWifiOff className="w-8 h-8 mx-auto mb-3 opacity-30" />
        <p className="text-sm">{t('access.disabled')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {showLocalIngress && (
        <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 space-y-2">
          <p className="text-sm font-bold text-indigo-300">{t('access.guide.title')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.lanFirst')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.tunnelWhen')}</p>
        </div>
      )}

      {/* 本地访问 */}
      <div className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <IconGlobe className="w-4 h-4" />
            {t('access.local')}
          </div>
          <button
            onClick={() => handleOpen(localUrl)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            title={t('access.open')}
          >
            <IconExternalLink className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2 bg-black/20 rounded-lg text-xs font-mono text-indigo-400">{localUrl}</code>
          <button
            onClick={() => handleCopy(localUrl, 'local')}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            title={t('access.copy')}
          >
            {copied === 'local' ? (
              <IconCheck className="w-4 h-4 text-emerald-500" />
            ) : (
              <IconCopy className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>

      {/* 内网访问（推荐） */}
      {showLocalIngress && (
        <div
          id="public-access"
          className="p-6 rounded-2xl bg-emerald-500/5 border border-emerald-500/25 space-y-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 text-sm font-bold text-foreground">
              <IconWifi className="w-4 h-4 text-emerald-400" />
              {t('access.lan.title')}
            </div>
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide bg-emerald-500/20 text-emerald-400">
              {t('access.lan.recommended')}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.lan.description')}</p>
          {remoteUrl ? (
            <>
              <div className="flex items-center gap-2">
                <code className="flex-1 min-w-0 px-3 py-2 bg-black/20 rounded-lg text-xs font-mono text-emerald-400 break-all">
                  {remoteUrl}
                </code>
                <button
                  type="button"
                  onClick={() => handleOpen(remoteUrl)}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('access.open')}
                >
                  <IconExternalLink className="w-4 h-4 text-muted-foreground" />
                </button>
                <button
                  type="button"
                  onClick={() => handleCopy(remoteUrl, 'lan')}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('access.copy')}
                >
                  {copied === 'lan' ? (
                    <IconCheck className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <IconCopy className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>
              {lanQrSrc ? (
                <div className="hidden md:flex flex-col items-center gap-2 pt-2">
                  <div className="p-3 bg-white rounded-xl">
                    <img src={lanQrSrc} alt={t('access.lan.qrAlt')} width={160} height={160} className="block" />
                  </div>
                  <p className="text-xs text-muted-foreground">{t('access.lan.scanHint')}</p>
                </div>
              ) : null}
              {!isTauriRuntime() && (
                <p className="text-xs text-amber-500/80 leading-relaxed">{t('access.lan.webDevHint')}</p>
              )}
              {isTauriRuntime() && !config.enableRemoteAccess && (
                <p className="text-xs text-amber-500/80 leading-relaxed">{t('access.lan.tauriEnableRemote')}</p>
              )}
            </>
          ) : (
            <p className="text-xs text-muted-foreground">{t('access.fetchingIP')}</p>
          )}
        </div>
      )}

      {/* 安全提示 */}
      {showLocalIngress && !config.requirePassword && isTauriRuntime() && config.enableRemoteAccess && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
          <IconLock className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-500/80 leading-relaxed">{t('access.securityWarning')}</p>
        </div>
      )}

      {/* 外网访问（可选） */}
      {showLocalIngress && (
        <details className="group p-6 rounded-2xl bg-white/5 border border-white/10 open:pb-6">
          <summary className="cursor-pointer list-none flex items-center justify-between gap-2 text-sm font-bold text-foreground">
            <span className="flex items-center gap-2">
              <IconGlobe className="w-4 h-4" />
              {t('access.tunnel.sectionTitle')}
            </span>
            <span className="text-xs font-normal text-muted-foreground group-open:hidden">
              {t('access.tunnel.sectionCollapsed')}
            </span>
          </summary>
          <div className="mt-4 space-y-3">
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.tunnel.whenNeeded')}</p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void handleStartTunnel()}
              disabled={isTunnelStarting || tunnelActive || !passwordProtectionEnabled}
              className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-colors"
            >
              {isTunnelStarting
                ? t('access.tunnel.startingButton')
                : tunnelActive
                  ? t('access.tunnel.runningButton')
                  : t('access.tunnel.startButton')}
            </button>
            <button
              type="button"
              onClick={() => void handleStopTunnel()}
              disabled={!isTunnelStarting && !tunnelActive}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-colors"
            >
              {t('access.tunnel.stopButton')}
            </button>
          </div>
          {!passwordProtectionEnabled && (
            <p className="text-xs text-amber-500/90">{t('access.tunnel.passwordRequired')}</p>
          )}
          {tunnelUrl && (
            <div className="pt-2 border-t border-white/10 space-y-2">
              <p className="text-xs text-muted-foreground">{t('access.tunnel.publicLink')}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 min-w-0 px-3 py-2 bg-black/20 rounded-lg text-xs font-mono text-emerald-400 break-all">
                  {tunnelUrl}
                </code>
                <button
                  type="button"
                  onClick={() => handleCopy(tunnelUrl, 'tunnel_url')}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors"
                  title={t('access.copy')}
                >
                  {copied === 'tunnel_url' ? (
                    <IconCheck className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <IconCopy className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>
              <div className="hidden md:flex flex-col items-center gap-2 pt-2">
                <div className="p-3 bg-white rounded-xl">
                  <img
                    src={`/webui/qrcode.png?url=${encodeURIComponent(tunnelUrl)}`}
                    alt={t('access.tunnel.qrAlt')}
                    width={160}
                    height={160}
                    className="block"
                  />
                </div>
                <p className="text-xs text-muted-foreground">{t('access.tunnel.scanHint')}</p>
              </div>
            </div>
          )}
          </div>
        </details>
      )}

      {showLocalIngress && (
        <details className="p-6 rounded-2xl bg-white/5 border border-white/10">
          <summary className="cursor-pointer list-none text-sm font-bold text-foreground">
            {t('access.stableDomain.title')}
          </summary>
          <div className="mt-3 space-y-2">
            <p className="text-xs text-muted-foreground leading-relaxed">{t('access.stableDomain.description')}</p>
            <ol className="list-decimal list-inside space-y-1 text-xs text-muted-foreground leading-relaxed">
              <li>{t('access.stableDomain.step1')}</li>
              <li>{t('access.stableDomain.step2')}</li>
              <li>{t('access.stableDomain.step3')}</li>
            </ol>
          </div>
        </details>
      )}

      <IngressEntitlementGate>
        <div className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <IconGlobe className="w-4 h-4" />
            {t('access.ingress.title')}
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.ingress.description')}</p>
          {tunnelActive && <p className="text-xs text-emerald-500/90">{t('access.ingress.syncedFromTunnel')}</p>}
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={publicIngressBaseUrl || ''}
              onChange={(e) => setPublicIngressBaseUrl(e.target.value)}
              readOnly={tunnelActive}
              placeholder="https://..."
              className={cn(
                'flex-1 px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50',
                tunnelActive && 'opacity-70 cursor-not-allowed',
              )}
            />
            <button
              type="button"
              onClick={() => void handleTestIngress()}
              disabled={testingIngress}
              className="px-4 py-2.5 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white rounded-xl text-sm font-bold transition-colors whitespace-nowrap"
            >
              {testingIngress ? t('access.ingress.testing') : t('access.ingress.testButton')}
            </button>
          </div>
        </div>
      </IngressEntitlementGate>
    </div>
  );
});
AccessCard.displayName = 'AccessCard';

const SystemSection = memo(() => {
  const t = useTranslations('settings.system');
  const isLocal = isLocalMode();
  const { config, currentMode, localIP, loading, saveConfig, saveAndRestart } = useSystemConfig();
  const [localConfig, setLocalConfig] = useState<SystemConfig>(DEFAULT_SYSTEM_CONFIG);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    if (!loading) {
      setLocalConfig(config);
    }
  }, [config, loading]);

  useEffect(() => {
    if (typeof window === 'undefined' || loading) {
      return;
    }
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) {
      return;
    }
    requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [loading]);

  const handleChange = <K extends keyof SystemConfig>(key: K, value: SystemConfig[K]) => {
    if (key === 'enableRemoteAccess' && value === true && !isTauriRuntime()) {
      toast.info(t('config.enableRemoteWebDevHint'));
    }
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setIsDirty(true);
  };

  const guardSave = useCallback(async (): Promise<boolean> => {
    try {
      await saveConfig(localConfig);
      setIsDirty(false);
      return true;
    } catch {
      return false;
    }
  }, [localConfig, saveConfig]);

  useDirtyGuard('system', { isDirty, onSave: guardSave });

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await saveConfig(localConfig);

      if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
        try {
          const { invoke } = await import('@tauri-apps/api/core');
          await invoke('update_global_shortcut', {
            shortcut: localConfig.globalShortcut,
            appshotShortcut: localConfig.appshotShortcut,
          });
        } catch (e) {
          console.error('Failed to update shortcuts:', e);
        }
      }

      setIsDirty(false);
      toast.success(t('saved'));
    } catch {
      toast.error(t('saveFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleRestart = async () => {
    if (!isDirty) {
      // 如果没有修改，直接重启
      setIsRestarting(true);
      toast.success(t('restarting'));
      try {
        await saveAndRestart(localConfig);
      } catch {
        toast.error(t('restartFailed'));
        setIsRestarting(false);
      }
    } else {
      // 如果有修改，保存并重启
      setIsRestarting(true);
      toast.success(t('restarting'));
      try {
        await saveAndRestart(localConfig);
        setIsDirty(false);
      } catch {
        toast.error(t('restartFailed'));
        setIsRestarting(false);
      }
    }
  };

  if (loading) {
    return <div className="h-40 w-full animate-pulse bg-white/5 rounded-3xl" />;
  }

  if (!isLocal) {
    return (
      <div className="max-w-4xl mx-auto py-4">
        <div className="p-8 rounded-2xl bg-white/5 border border-white/10 text-center">
          <IconSettings className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
          <h3 className="text-lg font-bold text-foreground mb-2">{t('desktopModeOnly')}</h3>
          <p className="text-sm text-muted-foreground">{t('desktopModeDescription')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-12 max-w-4xl mx-auto py-4">
      {/* 当前模式状态 */}
      <section className="relative group">
        <div className="absolute -inset-4 bg-gradient-to-tr from-indigo-500/10 to-transparent rounded-3xl blur-2xl opacity-50 group-hover:opacity-100 transition-opacity" />

        <div className="relative p-8 rounded-[2.5rem] bg-background/40 backdrop-blur-2xl border border-white/10 shadow-2xl">
          <div className="flex items-start justify-between mb-6">
            <div className="space-y-1">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-muted-foreground/50">
                {t('status.currentMode')}
              </p>
              <h3 className="text-3xl font-black text-foreground">{t('title')}</h3>
            </div>
            <ModeStatusBadge currentMode={currentMode} />
          </div>

          <p className="text-muted-foreground/80 leading-relaxed">{t('description')}</p>
        </div>
      </section>

      {/* WebUI 模式配置 */}
      <section className="space-y-6">
        <div className="flex items-center gap-3 px-2">
          <IconSettings className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
            {t('config.title')}
          </h2>
        </div>

        <div className="space-y-6 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
          {/* 关闭时隐藏到托盘 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.closeToTray')}</label>
              <p className="text-xs text-muted-foreground">{t('config.closeToTrayDesc')}</p>
            </div>
            <button
              onClick={() => handleChange('closeToTray', !localConfig.closeToTray)}
              className={cn(
                'relative w-12 h-6 rounded-full transition-colors',
                localConfig.closeToTray ? 'bg-indigo-500' : 'bg-white/10',
              )}
            >
              <div
                className={cn(
                  'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform',
                  localConfig.closeToTray && 'translate-x-6',
                )}
              />
            </button>
          </div>

          <div className="h-px bg-white/5" />

          {/* 全局唤醒快捷键 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.globalShortcut')}</label>
              <p className="text-xs text-muted-foreground">{t('config.globalShortcutDesc')}</p>
            </div>
            <ShortcutRecorder
              value={localConfig.globalShortcut}
              onChange={(value) => handleChange('globalShortcut', value)}
            />
          </div>

          <div className="h-px bg-white/5" />

          {/* Appshot 截屏快捷键 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.appshotShortcut')}</label>
              <p className="text-xs text-muted-foreground">{t('config.appshotShortcutDesc')}</p>
            </div>
            <ShortcutRecorder
              value={localConfig.appshotShortcut}
              onChange={(value) => handleChange('appshotShortcut', value)}
            />
          </div>

          <div className="h-px bg-white/5" />

          {/* 启用 WebUI 模式 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.enableWebUI')}</label>
              <p className="text-xs text-muted-foreground">{t('config.enableWebUIDesc')}</p>
            </div>
            <button
              onClick={() => handleChange('enableWebUIMode', !localConfig.enableWebUIMode)}
              className={cn(
                'relative w-12 h-6 rounded-full transition-colors',
                localConfig.enableWebUIMode ? 'bg-indigo-500' : 'bg-white/10',
              )}
            >
              <div
                className={cn(
                  'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform',
                  localConfig.enableWebUIMode && 'translate-x-6',
                )}
              />
            </button>
          </div>

          {/* 远程访问 */}
          {(localConfig.enableWebUIMode || isLocal) && (
            <>
              <div className="h-px bg-white/5" />
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-foreground">{t('config.enableRemote')}</label>
                  <p className="text-xs text-muted-foreground">{t('config.enableRemoteDesc')}</p>
                </div>
                <button
                  onClick={() => handleChange('enableRemoteAccess', !localConfig.enableRemoteAccess)}
                  className={cn(
                    'relative w-12 h-6 rounded-full transition-colors',
                    localConfig.enableRemoteAccess ? 'bg-indigo-500' : 'bg-white/10',
                  )}
                >
                  <div
                    className={cn(
                      'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform',
                      localConfig.enableRemoteAccess && 'translate-x-6',
                    )}
                  />
                </button>
              </div>

              {/* 端口配置 */}
              <div className="h-px bg-white/5" />
              <div className="grid grid-cols-2 gap-4">
                {/* 前端端口 */}
                <div className="space-y-3">
                  <label className="text-sm font-bold text-foreground">{t('config.webuiPort')}</label>
                  <input
                    type="number"
                    value={localConfig.webuiPort}
                    onChange={(e) => handleChange('webuiPort', Number.parseInt(e.target.value) || 3000)}
                    min={1024}
                    max={65535}
                    className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                  />
                  <p className="text-xs text-muted-foreground">{t('config.webuiPortDesc')}</p>
                </div>

                <div className="space-y-3">
                  <label className="text-sm font-bold text-foreground">{t('config.apiPort')}</label>
                  <input
                    type="number"
                    value={localConfig.apiPort}
                    onChange={(e) => handleChange('apiPort', Number.parseInt(e.target.value) || 25808)}
                    min={1024}
                    max={65535}
                    className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                  />
                  <p className="text-xs text-muted-foreground">{t('config.apiPortDesc')}</p>
                </div>
              </div>

              {/* 需要密码 */}
              <div className="h-px bg-white/5" />
              <div id="require-password" className="flex items-center justify-between">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-foreground">{t('config.requirePassword')}</label>
                  <p className="text-xs text-muted-foreground">{t('config.requirePasswordDesc')}</p>
                </div>
                <button
                  onClick={() => handleChange('requirePassword', !localConfig.requirePassword)}
                  className={cn(
                    'relative w-12 h-6 rounded-full transition-colors',
                    localConfig.requirePassword ? 'bg-indigo-500' : 'bg-white/10',
                  )}
                >
                  <div
                    className={cn(
                      'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform',
                      localConfig.requirePassword && 'translate-x-6',
                    )}
                  />
                </button>
              </div>
            </>
          )}

          {/* 配置变更提示 */}
          {isDirty && (
            <>
              <div className="h-px bg-white/5" />
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
                <IconRefresh className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-xs font-bold text-amber-500 mb-1">{t('config.restartRequired')}</p>
                  <p className="text-xs text-amber-500/80 leading-relaxed">{t('config.restartRequiredDesc')}</p>
                </div>
              </div>
            </>
          )}

          {/* 操作按钮 */}
          <div className="h-px bg-white/5" />
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={!isDirty || isSaving}
              className={cn(
                'flex-1 px-6 py-3 rounded-xl font-bold text-sm transition-all',
                isDirty
                  ? 'bg-indigo-500 text-white hover:bg-indigo-600'
                  : 'bg-white/5 text-muted-foreground cursor-not-allowed',
              )}
            >
              {isSaving ? t('saving') : t('save')}
            </button>
            <button
              onClick={handleRestart}
              disabled={isRestarting}
              className={cn(
                'px-6 py-3 rounded-xl border font-bold text-sm transition-all flex items-center gap-2',
                isDirty
                  ? 'bg-indigo-500 text-white hover:bg-indigo-600 border-indigo-500'
                  : 'bg-white/5 hover:bg-white/10 border-white/10',
              )}
            >
              {isRestarting ? <IconRefresh className="w-4 h-4 animate-spin" /> : <IconStop className="w-4 h-4" />}
              {isDirty ? t('saveAndRestart') : t('restart')}
            </button>
          </div>
        </div>
      </section>

      {/* 访问地址 */}
      <section className="space-y-6">
        <div className="flex items-center gap-3 px-2">
          <IconWifi className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
            {t('access.title')}
          </h2>
        </div>

        <AccessCard config={config} localIP={localIP} />
      </section>

      {/* Locked Use (Computer Use + Screen Lock) */}
      <LockedUseCard enabled={config.lockedUseEnabled} onToggle={(v) => handleChange('lockedUseEnabled', v)} />

      {/* Browser Pool */}
      <BrowserPoolCard />

      {/* Memory Monitor */}
      <MemoryMonitorCard />

      {/* System Doctor */}
      <DoctorDashboard />
    </div>
  );
});

SystemSection.displayName = 'SystemSection';

export default SystemSection;

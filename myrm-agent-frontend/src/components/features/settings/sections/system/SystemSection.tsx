'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconSettings,
  IconWifi,
  IconStop,
  IconRefresh,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import { SystemConfig, DEFAULT_SYSTEM_CONFIG } from '@/types/system';
import { useSystemConfig } from '@/hooks/useSystemConfig';
import { useDirtyGuard } from '@/hooks/useDirtyGuard';
import BrowserPoolCard from './BrowserPoolCard';
import { AccessCard } from './AccessCard';
import LockedUseCard from './LockedUseCard';
import MemoryMonitorCard from '../knowledge/MemoryMonitorCard';
import { DoctorDashboard } from '../../../health/DoctorDashboard';
import { fetchWebuiProtection, updateWebuiProtection } from '@/services/webui-auth';
import WebuiAccessSecurityPanel from './WebuiAccessSecurityPanel';
import { useIngressRequirement } from '@/hooks/useIngressRequirement';

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

const AppshotExcludedAppsEditor = memo<{
  apps: string[];
  onChange: (apps: string[]) => void;
}>(({ apps, onChange }) => {
  const t = useTranslations('settings.system.config');
  const [inputValue, setInputValue] = useState('');

  const handleAdd = useCallback(() => {
    const val = inputValue.trim();
    if (!val || apps.includes(val)) return;
    onChange([...apps, val]);
    setInputValue('');
  }, [inputValue, apps, onChange]);

  const handleRemove = useCallback(
    (idx: number) => {
      onChange(apps.filter((_, i) => i !== idx));
    },
    [apps, onChange],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAdd();
      }
    },
    [handleAdd],
  );

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <label className="text-sm font-bold text-foreground">{t('appshotPrivacyBlacklist')}</label>
        <p className="text-xs text-muted-foreground">{t('appshotPrivacyBlacklistDesc')}</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {apps.map((app, idx) => (
          <span
            key={`${app}-${idx}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-destructive/10 text-destructive border border-destructive/20"
          >
            {app}
            <button
              type="button"
              onClick={() => handleRemove(idx)}
              className="ml-0.5 hover:text-destructive/80 transition-colors"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('appshotAddAppPlaceholder')}
          className="flex-1 px-3 py-1.5 bg-muted/50 border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={!inputValue.trim()}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {t('appshotAddApp')}
        </button>
      </div>
    </div>
  );
});
AppshotExcludedAppsEditor.displayName = 'AppshotExcludedAppsEditor';

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

const SystemSection = memo(() => {
  const t = useTranslations('settings.system');
  const isLocal = isLocalMode();
  const ingressSnapshot = useIngressRequirement();
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
    if (!isLocal || loading) {
      return;
    }
    void fetchWebuiProtection()
      .then((cfg) => {
        setLocalConfig((prev) => ({ ...prev, requirePassword: cfg.require_password }));
      })
      .catch(() => {
        /* server may be offline during dev */
      });
  }, [isLocal, loading]);

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

  const handleRequirePasswordToggle = async () => {
    const next = !localConfig.requirePassword;
    handleChange('requirePassword', next);
    if (!isLocal) {
      return;
    }
    try {
      await updateWebuiProtection(next);
    } catch (err) {
      handleChange('requirePassword', !next);
      toast.error(err instanceof Error ? err.message : t('saveFailed'));
    }
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
      if (isLocal) {
        await updateWebuiProtection(localConfig.requirePassword);
      }

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

          {/* Appshot 隐私黑名单 */}
          <AppshotExcludedAppsEditor
            apps={localConfig.appshotExcludedApps ?? []}
            onChange={(apps) => handleChange('appshotExcludedApps', apps)}
          />

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
                  type="button"
                  onClick={() => void handleRequirePasswordToggle()}
                  className={cn(
                    'relative w-12 h-6 rounded-full transition-colors',
                    localConfig.requirePassword ? 'bg-primary' : 'bg-muted',
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

              {isLocal && <WebuiAccessSecurityPanel />}
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

        <AccessCard config={config} localIP={localIP} ingressSnapshot={ingressSnapshot} />
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

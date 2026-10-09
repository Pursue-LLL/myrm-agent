'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconWifi } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import { SystemConfig, DEFAULT_SYSTEM_CONFIG } from '@/types/system';
import { useSystemConfig } from '@/hooks/settings/useSystemConfig';
import { useDirtyGuard } from '@/hooks/ui/useDirtyGuard';
import BrowserPoolCard from './BrowserPoolCard';
import BrowserDoctorCard from './BrowserDoctorCard';
import BrowserProxyCard from './BrowserProxyCard';
import CaptchaSolverCard from './CaptchaSolverCard';
import CloudBrowserCard from './CloudBrowserCard';
import { AccessCard } from './AccessCard';
import LockedUseCard from './LockedUseCard';
import PrivacyCurtainCard from './PrivacyCurtainCard';
import SystemConfigCard from './SystemConfigCard';
import DesktopPermissionsCard from './DesktopPermissionsCard';
import MemoryMonitorCard from '../knowledge/MemoryMonitorCard';
import { DoctorDashboard } from '../../../health/DoctorDashboard';
import { fetchWebuiProtection, updateWebuiProtection } from '@/services/webui-auth';
import ServerConnectionCard from './ServerConnectionCard';
import StorageCard from './StorageCard';
import { useIngressRequirement } from '@/hooks/billing/useIngressRequirement';
import SandboxResetCard from './SandboxResetCard';
import DomainSkillsCard from './DomainSkillsCard';
import SavedSessionsCard from './SavedSessionsCard';
import PushNotificationCard from './PushNotificationCard';
import AgentCommerceBudgetSection from './AgentCommerceBudgetSection';

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
            voicePttShortcut: localConfig.voicePttShortcut ?? '',
          });
        } catch {
          toast.error(t('shortcutConflict'));
          return;
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

  const showApiPortInSettings = !isTauriRuntime() || localConfig.enableWebUIMode;

  if (!isLocal) {
    return (
      <div className="space-y-12 max-w-4xl mx-auto py-4">
        <SandboxResetCard />
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
      <SystemConfigCard
        localConfig={localConfig}
        isLocal={isLocal}
        isDirty={isDirty}
        isSaving={isSaving}
        isRestarting={isRestarting}
        showApiPortInSettings={showApiPortInSettings}
        onChange={handleChange}
        onRequirePasswordToggle={() => void handleRequirePasswordToggle()}
        onSave={handleSave}
        onRestart={handleRestart}
      />

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

      {/* Server Connection (Remote Gateway) */}
      <ServerConnectionCard />

      {/* Push Notifications */}
      <PushNotificationCard />

      {/* 存储位置 */}
      <StorageCard
        customDataDir={localConfig.customDataDir}
        onDataDirChange={(dir) => handleChange('customDataDir', dir)}
      />

      {/* Locked Use (Computer Use + Screen Lock) */}
      <LockedUseCard
        enabled={localConfig.lockedUseEnabled}
        onToggle={(v) => handleChange('lockedUseEnabled', v)}
      />

      {/* Privacy Curtain (unattended workstation shield) */}
      <PrivacyCurtainCard
        enabled={localConfig.privacyCurtainEnabled}
        onToggle={(v) => handleChange('privacyCurtainEnabled', v)}
      />

      {/* Desktop Permissions Diagnostic */}
      <DesktopPermissionsCard />

      {/* Browser Pool */}
      <BrowserPoolCard />

      <BrowserDoctorCard />

      {/* Cloud Browser Provider */}
      <CloudBrowserCard />

      {/* Browser Proxy */}
      <BrowserProxyCard />

      {/* CAPTCHA Auto-Solver */}
      <CaptchaSolverCard />

      {/* Domain Executable Skills */}
      <DomainSkillsCard />

      {/* Saved Browser Sessions */}
      <SavedSessionsCard />

      {/* Memory Monitor */}
      <MemoryMonitorCard />

      {/* Autonomous Commerce Budget & Spending Ledger */}
      <AgentCommerceBudgetSection />

      {/* System Doctor */}
      <DoctorDashboard />
    </div>
  );
});

SystemSection.displayName = 'SystemSection';

export default SystemSection;

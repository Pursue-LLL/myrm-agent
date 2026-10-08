'use client';

/**
 * 系统配置卡：托盘/开机启动/快捷键/空闲回收/WebUI 端口与访问密码，以及保存与重启操作。
 * 状态与持久化留在 SystemSection，本组件只负责呈现与回调。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconSettings, IconStop, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type { SystemConfig } from '@/types/system';
import Toggle from '../../common/Toggle';
import AppshotExcludedAppsEditor from './AppshotExcludedAppsEditor';
import ShortcutRecorder from './ShortcutRecorder';
import WebuiAccessSecurityPanel from './WebuiAccessSecurityPanel';

interface SystemConfigCardProps {
  localConfig: SystemConfig;
  isLocal: boolean;
  isDirty: boolean;
  isSaving: boolean;
  isRestarting: boolean;
  showApiPortInSettings: boolean;
  onChange: <K extends keyof SystemConfig>(key: K, value: SystemConfig[K]) => void;
  onRequirePasswordToggle: () => void;
  onSave: () => void;
  onRestart: () => void;
}

const SystemConfigCard = memo<SystemConfigCardProps>(
  ({
    localConfig,
    isLocal,
    isDirty,
    isSaving,
    isRestarting,
    showApiPortInSettings,
    onChange,
    onRequirePasswordToggle,
    onSave,
    onRestart,
  }) => {
    const t = useTranslations('settings.system');

    return (
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
            <Toggle
              checked={localConfig.closeToTray}
              onChange={() => onChange('closeToTray', !localConfig.closeToTray)}
              ariaLabel={t('config.closeToTray')}
            />
          </div>

          <div className="h-px bg-white/5" />

          {/* 开机自动启动 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.autoLaunchAtLogin')}</label>
              <p className="text-xs text-muted-foreground">{t('config.autoLaunchAtLoginDesc')}</p>
            </div>
            <Toggle
              checked={localConfig.autoLaunchAtLogin}
              onChange={() => onChange('autoLaunchAtLogin', !localConfig.autoLaunchAtLogin)}
              ariaLabel={t('config.autoLaunchAtLogin')}
            />
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
              onChange={(value) => onChange('globalShortcut', value)}
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
              onChange={(value) => onChange('appshotShortcut', value)}
            />
          </div>

          <div className="h-px bg-white/5" />

          {/* Voice PTT 快捷键 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.voicePttShortcut')}</label>
              <p className="text-xs text-muted-foreground">{t('config.voicePttShortcutDesc')}</p>
            </div>
            <ShortcutRecorder
              value={localConfig.voicePttShortcut ?? ''}
              onChange={(value) => onChange('voicePttShortcut', value)}
            />
          </div>

          {/* Appshot 隐私黑名单 */}
          <AppshotExcludedAppsEditor
            apps={localConfig.appshotExcludedApps ?? []}
            onChange={(apps) => onChange('appshotExcludedApps', apps)}
          />

          <div className="h-px bg-white/5" />

          {/* 会话空闲重资源回收 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.idleReclaim')}</label>
              <p className="text-xs text-muted-foreground">{t('config.idleReclaimDesc')}</p>
            </div>
            <select
              value={localConfig.idleReclaimTimeoutSeconds ?? 1800}
              onChange={(e) => onChange('idleReclaimTimeoutSeconds', Number.parseInt(e.target.value) || 0)}
              className="px-3 py-1.5 bg-black/20 border border-white/10 rounded-lg text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              <option value={900}>{t('config.idleReclaim15m')}</option>
              <option value={1800}>{t('config.idleReclaim30m')}</option>
              <option value={3600}>{t('config.idleReclaim1h')}</option>
              <option value={0}>{t('config.idleReclaimNever')}</option>
            </select>
          </div>

          <div className="h-px bg-white/5" />

          {/* 启用 WebUI 模式 */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-bold text-foreground">{t('config.enableWebUI')}</label>
              <p className="text-xs text-muted-foreground">{t('config.enableWebUIDesc')}</p>
            </div>
            <Toggle
              checked={localConfig.enableWebUIMode}
              onChange={() => onChange('enableWebUIMode', !localConfig.enableWebUIMode)}
              ariaLabel={t('config.enableWebUI')}
            />
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
                <Toggle
                  checked={localConfig.enableRemoteAccess}
                  onChange={() => onChange('enableRemoteAccess', !localConfig.enableRemoteAccess)}
                  ariaLabel={t('config.enableRemote')}
                />
              </div>

              {/* 端口配置 */}
              <div className="h-px bg-white/5" />
              <div className={cn('grid gap-4', showApiPortInSettings ? 'grid-cols-2' : 'grid-cols-1')}>
                {/* 前端端口 */}
                <div className="space-y-3">
                  <label className="text-sm font-bold text-foreground">{t('config.webuiPort')}</label>
                  <input
                    type="number"
                    value={localConfig.webuiPort}
                    onChange={(e) => onChange('webuiPort', Number.parseInt(e.target.value) || 3000)}
                    min={1024}
                    max={65535}
                    className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                  />
                  <p className="text-xs text-muted-foreground">{t('config.webuiPortDesc')}</p>
                </div>

                {showApiPortInSettings && (
                  <div className="space-y-3">
                    <label className="text-sm font-bold text-foreground">{t('config.apiPort')}</label>
                    <input
                      type="number"
                      value={localConfig.apiPort}
                      onChange={(e) => onChange('apiPort', Number.parseInt(e.target.value) || 25808)}
                      min={1024}
                      max={65535}
                      className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                    />
                    <p className="text-xs text-muted-foreground">{t('config.apiPortDesc')}</p>
                  </div>
                )}
              </div>

              {/* 需要密码 */}
              <div className="h-px bg-white/5" />
              <div id="require-password" className="flex items-center justify-between">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-foreground">{t('config.requirePassword')}</label>
                  <p className="text-xs text-muted-foreground">{t('config.requirePasswordDesc')}</p>
                </div>
                <Toggle
                  checked={localConfig.requirePassword}
                  onChange={onRequirePasswordToggle}
                  ariaLabel={t('config.requirePassword')}
                />
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
              onClick={onSave}
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
              onClick={onRestart}
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
    );
  },
);
SystemConfigCard.displayName = 'SystemConfigCard';

export default SystemConfigCard;

/**
 * 系统配置管理 Hook
 *
 * 提供系统配置的加载、保存、重置等功能
 * 仅在 Tauri 环境下可用
 */

import { useState, useEffect } from 'react';
import { SystemConfig, DEFAULT_SYSTEM_CONFIG, RunMode } from '@/types/system';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { loadWebuiAccessPrefs, saveWebuiAccessPrefs } from '@/lib/webui-access-prefs';

// 动态导入 Tauri API，避免在 Web 环境下报错
const getTauriInvoke = async (): Promise<typeof import('@tauri-apps/api/core').invoke | null> => {
  // 必须在真正的 Tauri 运行时中才能调用 invoke
  if (!isTauriRuntime()) return null;
  try {
    const tauriCore = await import('@tauri-apps/api/core');
    if (!tauriCore || !tauriCore.invoke) {
      console.error('Tauri core imported but invoke function not found');
      return null;
    }
    return tauriCore.invoke;
  } catch (error) {
    console.error('Failed to import Tauri API:', error);
    return null;
  }
};

export function useSystemConfig() {
  const [config, setConfig] = useState<SystemConfig>(DEFAULT_SYSTEM_CONFIG);
  const [currentMode, setCurrentMode] = useState<RunMode>('desktop');
  const [localIP, setLocalIP] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载配置
  const loadConfig = async () => {
    // 非 Tauri 运行时环境，直接返回默认配置
    if (!isTauriRuntime()) {
      const prefs = loadWebuiAccessPrefs();
      setConfig(
        prefs
          ? { ...DEFAULT_SYSTEM_CONFIG, enableRemoteAccess: prefs.enableRemoteAccess }
          : DEFAULT_SYSTEM_CONFIG,
      );
      setCurrentMode('desktop');
      setLocalIP('');
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const invoke = await getTauriInvoke();
      if (!invoke) {
        throw new Error('Tauri invoke not available - running in web mode');
      }

      const [loadedConfig, mode, ip] = await Promise.all([
        invoke<SystemConfig>('load_system_config'),
        invoke<string>('get_current_mode'),
        invoke<string>('get_local_ip').catch(() => ''),
      ]);

      setConfig(loadedConfig);
      setCurrentMode(mode as RunMode);
      setLocalIP(ip);

      try {
        localStorage.setItem('myrm-tauri-system-config', JSON.stringify(loadedConfig));
      } catch {
        // ignore quota / private mode
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Failed to load config: ${message}`);
      console.error('Failed to load system config:', err);
      // 设置默认值
      setConfig(DEFAULT_SYSTEM_CONFIG);
      setCurrentMode('desktop');
      setLocalIP('');
    } finally {
      setLoading(false);
    }
  };

  // 保存配置
  const saveConfig = async (newConfig: SystemConfig) => {
    if (!isTauriRuntime()) {
      saveWebuiAccessPrefs({ enableRemoteAccess: newConfig.enableRemoteAccess });
      setConfig(newConfig);
      setError(null);
      return true;
    }

    try {
      setSaving(true);
      setError(null);

      const invoke = await getTauriInvoke();
      if (!invoke) {
        throw new Error('Tauri invoke not available');
      }

      await invoke('save_system_config', { config: newConfig });
      setConfig(newConfig);

      try {
        localStorage.setItem('myrm-tauri-system-config', JSON.stringify(newConfig));
      } catch {
        // ignore quota / private mode
      }

      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Failed to save config: ${message}`);
      console.error('Failed to save system config:', err);
      return false;
    } finally {
      setSaving(false);
    }
  };

  // 重置配置
  const resetConfig = async () => {
    if (!isTauriRuntime()) {
      setError('Not available in web mode');
      return false;
    }

    try {
      setSaving(true);
      setError(null);

      const invoke = await getTauriInvoke();
      if (!invoke) {
        throw new Error('Tauri invoke not available');
      }

      const defaultConfig = await invoke<SystemConfig>('reset_system_config');
      setConfig(defaultConfig);

      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Failed to reset config: ${message}`);
      console.error('Failed to reset system config:', err);
      return false;
    } finally {
      setSaving(false);
    }
  };

  // 保存并重启应用
  const saveAndRestart = async (newConfig: SystemConfig) => {
    if (!isTauriRuntime()) {
      setError('Not available in web mode');
      return false;
    }

    try {
      setSaving(true);
      setError(null);

      const invoke = await getTauriInvoke();
      if (!invoke) {
        throw new Error('Tauri invoke not available');
      }

      // 保存配置
      await invoke('save_system_config', { config: newConfig });

      // 重启应用
      await invoke('restart_app');

      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Failed to save and restart: ${message}`);
      console.error('Failed to save and restart:', err);
      return false;
    } finally {
      setSaving(false);
    }
  };

  // 初始化加载
  useEffect(() => {
    loadConfig();
  }, []);

  return {
    config,
    currentMode,
    localIP,
    loading,
    saving,
    error,
    loadConfig,
    saveConfig,
    resetConfig,
    saveAndRestart,
  };
}

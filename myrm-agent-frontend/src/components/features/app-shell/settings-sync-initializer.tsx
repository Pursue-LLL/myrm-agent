'use client';

/**
 * 配置同步初始化组件
 *
 * 在应用顶层挂载，自动处理用户配置的同步。
 *
 * 工作流程：
 * 1. 初始化 ConfigSyncManager（统一管理所有配置）
 * 2. 设置冲突解决器（UI 对话框）
 * 3. 初始化各个 Store（从 ConfigSyncManager 加载数据）
 *
 * 支持的部署模式：
 * - Tauri 模式：同步到本地 SQLite
 * - Sandbox 模式：同步到云端数据库（敏感数据服务端加密）
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { useCommandStore } from '@/store/useCommandStore';
import { useRetrievalStore } from '@/store/useRetrievalStore';
import { getConfigSyncManager } from '@/services/config';
import ConfigConflictDialog, { type ConfigConflictData } from './ConfigConflictDialog';

/**
 * 配置初始化状态
 */
type InitStatus = 'idle' | 'loading' | 'success' | 'error';

export default function SettingsSyncInitializer() {
  const t = useTranslations('configConflict');
  const [status, setStatus] = useState<InitStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  // 冲突对话框状态
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
  const [currentConflict, setCurrentConflict] = useState<ConfigConflictData | null>(null);
  const [conflictResolveCallback, setConflictResolveCallback] = useState<((keepLocal: boolean) => void) | null>(null);

  const { initProviders } = useProviderStore();
  const { initConfig } = useConfigStore();
  const { initCommands } = useCommandStore();
  const { initRetrieval } = useRetrievalStore();

  useEffect(() => {
    const initializeAll = async () => {
      if (status !== 'idle') return;

      setStatus('loading');

      try {
        // 先初始化 ConfigSyncManager，再初始化各个 Store
        console.log('[SettingsSync] Initializing ConfigSyncManager...');
        const manager = getConfigSyncManager();

        // 🎨 设置精美的冲突解决器（替换原生 window.confirm）
        manager.setConflictResolver?.((conflict) => {
          return new Promise<boolean>((resolve) => {
            const configLabel = getConfigKeyLabel(conflict.configKey);
            setCurrentConflict({
              configKey: conflict.configKey,
              configLabel,
              serverVersion: conflict.serverVersion,
              localVersion: conflict.localVersion,
              deviceId: conflict.deviceId,
              localValue: conflict.localValue,
              serverValue: conflict.serverValue,
            });
            setConflictResolveCallback(() => (keepLocal: boolean) => {
              resolve(keepLocal);
            });
            setConflictDialogOpen(true);
          });
        });

        await manager.initialize();
        await manager.runStartupNormalization();

        console.log('[SettingsSync] Initializing critical stores...');
        await initConfig();
        setStatus('success');

        const scheduleDeferred =
          typeof window !== 'undefined'
            ? window.requestIdleCallback ??
              ((callback: () => void) => {
                window.setTimeout(callback, 1);
              })
            : null;

        const runDeferredStores = () => {
          void Promise.all([initProviders(), initCommands(), initRetrieval()])
            .then(() => {
              console.log('[SettingsSync] Deferred stores initialized successfully');
            })
            .catch((deferredError) => {
              console.warn('[SettingsSync] Deferred store initialization failed:', deferredError);
            });
        };

        if (scheduleDeferred) {
          scheduleDeferred(runDeferredStores);
        } else {
          await Promise.all([initProviders(), initCommands(), initRetrieval()]);
        }
      } catch (err) {
        console.warn('[SettingsSync] Initialization failed:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
        setStatus('error');

        // 即使失败，也尝试初始化各个 Store（使用默认值）
        try {
          await initConfig();
          await Promise.all([initProviders(), initCommands(), initRetrieval()]);
        } catch {
          /* ignore secondary errors */
        }
      }
    };

    initializeAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 在开发模式下显示初始化状态
  if (process.env.NODE_ENV === 'development' && status === 'error') {
    console.warn('[SettingsSync] Error:', error);
  }

  const handleConflictResolution = (keepLocal: boolean) => {
    conflictResolveCallback?.(keepLocal);
    setConflictDialogOpen(false);
    setCurrentConflict(null);
    setConflictResolveCallback(null);
  };

  return (
    <ConfigConflictDialog
      open={conflictDialogOpen}
      onOpenChange={setConflictDialogOpen}
      conflict={currentConflict}
      onKeepLocal={() => handleConflictResolution(true)}
      onUseServer={() => handleConflictResolution(false)}
      t={t}
    />
  );
}

/**
 * 配置键的用户友好标签（国际化）
 */
function getConfigKeyLabel(key: string): string {
  const labelMap: Record<string, string> = {
    providers: 'Model Providers',
    chatSettings: 'Chat Settings',
    personalSettings: 'Personal Settings',
    mcpServers: 'MCP Servers',
    searchServices: 'Search Services',
    commands: 'Custom Commands',
    retrieval: 'Retrieval Config',
    channels: 'Notification Channels',
    voice: 'Voice Settings',
    securityConfig: 'Security Policy',
    feishuCredentials: 'Feishu Credentials',
    dingtalkCredentials: 'DingTalk Credentials',
    slackCredentials: 'Slack Credentials',
    discordCredentials: 'Discord Credentials',
    wecomCredentials: 'WeCom Credentials',
    wechatCredentials: 'WeChat Credentials',
    teamsCredentials: 'Teams Credentials',
    matrixCredentials: 'Matrix Credentials',
    telegramCredentials: 'Telegram Credentials',
    googlechatCredentials: 'Google Chat Credentials',
  };
  return labelMap[key] || key;
}

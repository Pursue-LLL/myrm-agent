/**
 * [INPUT]
 * - `@/services/config` getConfigSyncManager (POS: 配置同步单例)
 * - `@/lib/platform-readiness` whenDatabaseReady (POS: 后端数据库就绪门)
 * - `@/store/use*Store` init 动作（POS: 各配置 Store 的首次加载）
 *
 * [OUTPUT]
 * bootstrapSettingsSync: 应用启动时的配置同步顺序，不会 reject。
 *
 * [POS]
 * 先等数据库就绪，再启动 ConfigSyncManager 并装上冲突解决器，随后加载关键配置；其余 Store 等浏览器空闲再加载。
 * 任何一步失败都会退回「各 Store 直接用默认值启动」，数据库未就绪时则什么都不启动。
 */
import { whenDatabaseReady } from '@/lib/platform-readiness';
import { scheduleWhenIdle } from '@/lib/utils/scheduleWhenIdle';
import { getConfigSyncManager } from '@/services/config';
import type { ConfigConflictResolver } from '@/services/config/conflictResolution';
import { enforceSecurityPresetYoloMutex } from '@/store/chat/securityPreset';
import useChatStore from '@/store/useChatStore';
import { useCommandStore } from '@/store/useCommandStore';
import useConfigStore from '@/store/useConfigStore';
import useProviderStore from '@/store/useProviderStore';
import { useRetrievalStore } from '@/store/useRetrievalStore';

/** 首屏不需要的 Store：模型服务商、自定义命令、检索配置。 */
function initSecondaryStores(): Promise<unknown> {
  return Promise.all([
    useProviderStore.getState().initProviders(),
    useCommandStore.getState().initCommands(),
    useRetrievalStore.getState().initRetrieval(),
  ]);
}

export async function bootstrapSettingsSync(resolveConflict: ConfigConflictResolver): Promise<void> {
  try {
    if (!(await whenDatabaseReady())) {
      console.warn('[SettingsSync] Backend not available; configuration sync was not started');
      return;
    }

    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolveConflict);
    await manager.initialize();
    await manager.runStartupNormalization();

    // securityConfig 就绪后重放「非 HITL 预设 ⇄ YOLO」互斥：异步加载期间若已绑定非 HITL 预设 Agent，
    // disarm 因本地缓存未同步而跳过，此处兜底关闭残留 YOLO；运行时 securityConfig 变化（如其他 Tab 开启 YOLO）同样重放。
    enforceSecurityPresetYoloMutex(useChatStore.getState().securityPreset);
    manager.subscribe('securityConfig', () => {
      enforceSecurityPresetYoloMutex(useChatStore.getState().securityPreset);
    });

    await useConfigStore.getState().initConfig();

    scheduleWhenIdle(() => {
      void initSecondaryStores().catch((error: unknown) => {
        console.warn('[SettingsSync] Deferred store initialization failed:', error);
      });
    });
  } catch (error) {
    console.warn('[SettingsSync] Initialization failed:', error);

    // 即使失败，也让各个 Store 用默认值启动。
    try {
      await useConfigStore.getState().initConfig();
      await initSecondaryStores();
    } catch {
      /* ignore secondary errors */
    }
  }
}

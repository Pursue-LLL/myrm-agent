import { getConfigSyncManager, type RetrievalConfigValue } from '@/services/config';
import type { RetrievalConfig } from './types';

/**
 * 同步到 ConfigSyncManager
 *
 * 统一通过 ConfigSyncManager 同步：
 * - Tauri 模式：TauriAdapter -> SQLite
 * - Sandbox 模式：SandboxAdapter -> PostgreSQL + 服务端加密
 */
export function syncToManager(config: RetrievalConfig): void {
  const value: RetrievalConfigValue = {
    embeddingConfig: config.embeddingConfig,
    embeddingApplied: config.embeddingApplied,
    embeddingAppliedAt: config.embeddingAppliedAt,
    rerankerConfig: config.rerankerConfig,
    rerankerApplied: config.rerankerApplied,
    rerankerAppliedAt: config.rerankerAppliedAt,
    enableAdvancedRetrieval: config.enableAdvancedRetrieval,
  };
  getConfigSyncManager().set('retrieval', value);
}

/**
 * 旧记忆估算由服务端按「已保存的」检索配置回答，所以必须排在刚入队的这次保存之后。
 * 保存没成功就不估算：此时服务端仍按旧配置回答 0，会把迁移提示藏起来；提示挂载时会自己再查一次。
 */
export async function estimateOrphansOnceSaved(estimate: () => Promise<void>): Promise<void> {
  let saved = false;
  try {
    saved = (await getConfigSyncManager().forceSync()).success;
  } catch {
    // 同步管理器已记录失败原因；这里只需跳过估算。
  }
  if (saved) {
    await estimate();
  }
}

/**
 * [INPUT]
 * @/services/config::getConfigSyncManager (POS: 配置同步管理器)
 * @/store/chat/types/chatState::SecurityPreset (POS: 会话安全预设类型)
 *
 * [OUTPUT]
 * disarmYoloForPreset: 选择非 HITL 预设时关闭 YOLO 模式（互斥规则）
 *
 * [POS]
 * 安全预设与 YOLO 模式的互斥规则。会话内手动选择与 Agent 默认预设初始化共用此规则，
 * 保证「开启 accept_edits/explore 时 YOLO 自动关闭」在任何入口都一致生效。
 */
import { getConfigSyncManager } from '@/services/config';
import type { SecurityPreset } from '@/store/chat/types/chatState';

export function disarmYoloForPreset(preset: SecurityPreset): void {
  if (preset === 'hitl') return;

  const syncManager = getConfigSyncManager();
  const config = syncManager.get('securityConfig');
  if (config?.yoloModeEnabled) {
    syncManager.set('securityConfig', {
      ...config,
      yoloModeEnabled: false,
      yoloModeTimeout: undefined,
      yoloModeEnabledAt: undefined,
    });
  }
}

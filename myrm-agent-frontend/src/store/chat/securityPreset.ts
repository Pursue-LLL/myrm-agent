/**
 * [INPUT]
 * @/services/config::getConfigSyncManager (POS: 配置同步管理器)
 * @/store/chat/types/chatState::SecurityPreset (POS: 会话安全预设类型)
 *
 * [OUTPUT]
 * normalizeSecurityPreset: 会话安全预设归一化（非法/缺省回落 hitl）
 * isYoloEnabled / disableYolo: 全局 YOLO 模式读取与关闭（互斥规则的底层原语）
 * disarmYoloForPreset: 进入非 HITL 预设时关闭 YOLO（Agent 默认初始化入口）
 * resolvePresetWithYoloMutex: 选择器交互的互斥决策（会话内手动选择入口）
 *
 * [POS]
 * 安全预设与 YOLO 模式的互斥规则。会话内手动选择、Agent 默认预设初始化与进入聊天重置共用，
 * 保证「开启 accept_edits/explore 时 YOLO 自动关闭」「选择器任何操作先关闭 YOLO」
 * 与「无有效预设时回落 hitl」在任何入口都一致生效。
 */
import { getConfigSyncManager } from '@/services/config';
import type { SecurityPreset } from '@/store/chat/types/chatState';

export function normalizeSecurityPreset(value: SecurityPreset | null | undefined): SecurityPreset {
  return value === 'hitl' || value === 'accept_edits' || value === 'explore' ? value : 'hitl';
}

export function isYoloEnabled(): boolean {
  const syncManager = getConfigSyncManager();
  return syncManager.get('securityConfig')?.yoloModeEnabled ?? false;
}

export function disableYolo(): void {
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

export function disarmYoloForPreset(preset: SecurityPreset): void {
  if (preset === 'hitl') return;
  disableYolo();
}

/**
 * 选择器交互的互斥决策：YOLO 开启时任何选择（含点击当前项）都先关闭 YOLO，
 * 避免「显示 hitl=手动审批但实际全部自动批准」的安全假象。
 * 返回 null 表示不改变会话预设（仅关闭 YOLO 或完全无操作），否则返回生效的新预设。
 */
export function resolvePresetWithYoloMutex(
  current: SecurityPreset,
  next: SecurityPreset,
): SecurityPreset | null {
  if (isYoloEnabled()) {
    disableYolo();
    if (next === current) return null;
  } else if (next === current) {
    return null;
  }
  return next;
}

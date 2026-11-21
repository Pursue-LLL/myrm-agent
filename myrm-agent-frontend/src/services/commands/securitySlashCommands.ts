/**
 * [INPUT]
 * - @/services/config::getConfigSyncManager (POS: 安全配置的跨端同步管理器)
 * - @/lib/api::apiRequest (POS: 紧急停止接口)
 * - @/services/i18nToastService::showI18nToast (POS: i18n toast 封装)
 *
 * [OUTPUT]
 * - executeYoloSlashCommand: 执行 /yolo 命令（切换 YOLO 模式，可带超时时长）
 * - executeFreezeSlashCommand: 执行 /freeze 命令（激活或解除紧急停止）
 *
 * [POS]
 * 改变安全姿态的原生 Slash 命令执行服务。供 builtinActions 调用。
 */

import { toast } from 'sonner';
import { showI18nToast } from '@/services/i18nToastService';
import type { ActionResult } from '@/types/command';

function parseYoloArgs(inputValue: string): { action: 'toggle' | 'on' | 'off'; timeout?: number } {
  const args = inputValue
    .replace(/^\/yolo\s*/i, '')
    .trim()
    .toLowerCase();
  if (!args) {
    return { action: 'toggle' };
  }
  if (args === 'on') {
    return { action: 'on' };
  }
  if (args === 'off') {
    return { action: 'off' };
  }

  const timeoutMatch = args.match(/^(?:on\s+)?(\d+)\s*([smh]?)$/);
  if (timeoutMatch) {
    let seconds = parseInt(timeoutMatch[1], 10);
    const unit = timeoutMatch[2] || 's';
    if (unit === 'm') {
      seconds *= 60;
    } else if (unit === 'h') {
      seconds *= 3600;
    }
    return { action: 'on', timeout: seconds };
  }
  return { action: 'toggle' };
}

export async function executeYoloSlashCommand(inputValue: string): Promise<ActionResult> {
  const { getConfigSyncManager } = await import('@/services/config');
  const syncManager = getConfigSyncManager();
  const config = syncManager.get('securityConfig');
  if (!config) {
    return { success: false, error: 'Security config not loaded yet' };
  }
  const { action, timeout } = parseYoloArgs(inputValue);

  const currentlyEnabled = config.yoloModeEnabled ?? false;

  let newEnabled: boolean;
  if (action === 'toggle') {
    newEnabled = !currentlyEnabled;
  } else if (action === 'on') {
    newEnabled = true;
  } else {
    newEnabled = false;
  }

  syncManager.set('securityConfig', {
    ...config,
    yoloModeEnabled: newEnabled,
    ...(newEnabled && timeout ? { yoloModeTimeout: timeout } : { yoloModeTimeout: undefined }),
    ...(newEnabled ? { yoloModeEnabledAt: Math.floor(Date.now() / 1000) } : { yoloModeEnabledAt: undefined }),
  });

  if (newEnabled) {
    const suffix = timeout ? ` (${timeout}s)` : '';
    showI18nToast('commands.builtin.yoloEnabled', { timeout: suffix }, { type: 'warning' });
  } else {
    showI18nToast('commands.builtin.yoloDisabled', undefined, { type: 'success' });
  }

  return { success: true, newInputValue: '' };
}

export async function executeFreezeSlashCommand(inputValue: string): Promise<ActionResult> {
  const { apiRequest } = await import('@/lib/api');
  const args = inputValue
    .replace(/^\/freeze\s*/i, '')
    .trim()
    .toLowerCase();
  const shouldResume = args === 'off' || args === 'resume';

  const toastId = toast.loading('…');
  try {
    await apiRequest<{ level: string; reason: string }>('/security/estop', {
      method: 'POST',
      body: JSON.stringify(
        shouldResume ? { action: 'resume' } : { action: 'activate', reason: 'User triggered /freeze' },
      ),
    });

    toast.dismiss(toastId);
    if (shouldResume) {
      showI18nToast('commands.builtin.freezeResumed', undefined, { type: 'success' });
    } else {
      showI18nToast('commands.builtin.freezeActivated', undefined, { type: 'warning' });
    }
    window.dispatchEvent(new Event('estop-changed'));
    return { success: true, newInputValue: '' };
  } catch (e) {
    toast.dismiss(toastId);
    const msg = e instanceof Error ? e.message : 'Unknown error';
    showI18nToast('commands.builtin.freezeFailed', undefined, { type: 'error' });
    return { success: false, error: msg };
  }
}

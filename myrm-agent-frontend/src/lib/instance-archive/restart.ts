/**
 * [INPUT]
 * - @/lib/deploy-mode: isTauriRuntime, isRemoteGatewayActive
 * - @/lib/tauri: invokeTauriCommand
 * - @/lib/api: apiRequest
 *
 * [OUTPUT]
 * - RestartPlan, planRestart, performRestart
 *
 * [POS]
 * A queued restore or import is applied by the backend while it boots, so the user must
 * restart it. The desktop app and sandbox deployments can do that on request; a bare local
 * process has no supervisor, so the user is asked to restart it themselves.
 */

import { apiRequest } from '@/lib/api';
import { isRemoteGatewayActive, isTauriRuntime } from '@/lib/deploy-mode';
import { invokeTauriCommand } from '@/lib/tauri';
import type { RestartMode } from '@/services/instanceArchive';

export type RestartPlan = 'desktop' | 'sandbox' | 'manual';

export function planRestart(mode: RestartMode): RestartPlan {
  if (isTauriRuntime() && !isRemoteGatewayActive()) {
    return 'desktop';
  }
  return mode === 'sandbox' ? 'sandbox' : 'manual';
}

export async function performRestart(plan: Exclude<RestartPlan, 'manual'>): Promise<void> {
  if (plan === 'desktop') {
    await invokeTauriCommand('restart_app');
    return;
  }
  await apiRequest('/system/sandbox/recreate', { method: 'POST', silent: true });
}

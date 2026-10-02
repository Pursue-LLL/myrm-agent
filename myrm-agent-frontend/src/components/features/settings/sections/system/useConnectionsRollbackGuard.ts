/**
 * [INPUT]
 * - @/lib/deploy-mode::isTauriRuntime / getRemoteGatewayConfig / setRemoteGatewayConfig (POS: 前端部署模式与基础地址解析层)
 * - @/lib/remote-profiles::listRemoteProfiles / getActiveRemoteProfileId / setActiveRemoteProfileId (POS: Tauri Remote Profile 多槽档案 SSOT)
 * - @/lib/remote-follow-switch::switchRemoteFollow (POS: remote_follow 切换唯一前端入口)
 * - @/lib/connection-switch-guard (POS: 连接切换守卫存储)
 * - @/lib/utils/toast::toast (POS: 全局提示)
 *
 * [OUTPUT]
 * - useConnectionsRollbackGuard: reload 后 pending 切换复验与回滚 Hook。
 * - testRemoteHealth: 远程连接健康探测（连接守卫域共享）。
 *
 * [POS]
 * 连接切换复验回滚单一职责 Hook。挂载于 ServerConnectionCard：reload 后对
 * pending 切换做目标可达性复验，不可达则按 last-good 回滚（roster id 精确
 * 恢复，本地回滚显式重启本地后端，remote 间回滚手动刷新页面）。
 */

'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import {
  clearPendingSwitch,
  getLastGood,
  getPendingSwitch,
  isPendingFresh,
  setLastGood,
} from '@/lib/connection-switch-guard';
import {
  getActiveRemoteProfileId,
  listRemoteProfiles,
  setActiveRemoteProfileId,
} from '@/lib/remote-profiles';
import {
  isTauriRuntime,
  getRemoteGatewayConfig,
  setRemoteGatewayConfig,
} from '@/lib/deploy-mode';
import { switchRemoteFollow } from '@/lib/remote-follow-switch';

export async function testRemoteHealth(url: string): Promise<boolean> {
  try {
    const res = await fetch(`${url}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(8000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

interface ConnectionsRollbackGuardOptions {
  /** 回滚完成后刷新组件 roster/active 状态。 */
  onRestored: () => void;
}

export function useConnectionsRollbackGuard({ onRestored }: ConnectionsRollbackGuardOptions): void {
  const t = useTranslations('settings.system.serverConnection');

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }
    const pending = getPendingSwitch();
    if (!pending || !isPendingFresh(pending)) {
      clearPendingSwitch();
      return;
    }
    const current = getRemoteGatewayConfig();
    const targetUrl = current?.url ?? null;
    // Only verify switches initiated by the connection card (pending target matches live config).
    if (targetUrl !== pending.url) {
      clearPendingSwitch();
      return;
    }
    let cancelled = false;
    void (async () => {
      const healthy = targetUrl === null || (await testRemoteHealth(targetUrl));
      if (cancelled) {
        return;
      }
      if (healthy) {
        setLastGood({ activeId: getActiveRemoteProfileId(), url: targetUrl });
        clearPendingSwitch();
        return;
      }
      // Restore by roster id: stored urls are resolved API bases, which differ
      // from raw profile urls for cloud profiles. Rollback never writes new
      // profiles; unknown ids fall back to local.
      const lastGood = getLastGood();
      const profiles = listRemoteProfiles();
      const byId = lastGood?.activeId ? profiles.find((p) => p.id === lastGood.activeId) : undefined;
      const byUrl = lastGood?.url ? profiles.find((p) => p.url === lastGood.url) : undefined;
      const restoreId = byId?.id ?? byUrl?.id ?? null;
      let rolledBackToLocal = false;
      if (restoreId === null) {
        setRemoteGatewayConfig(null);
        rolledBackToLocal = true;
        // 回滚到本地：显式重启本地后端（remote_follow flag 复位）。
        await switchRemoteFollow(false);
      } else {
        setActiveRemoteProfileId(restoreId);
      }
      clearPendingSwitch();
      onRestored();
      toast.error(t('restoredLastGood'));
      if (!rolledBackToLocal) {
        // 仅 remote→remote 回滚需手动刷新；本地回滚由 switch 的
        // `app:connections-changed` 事件统一驱动（含 session windows）。
        window.location.reload();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t, onRestored]);
}

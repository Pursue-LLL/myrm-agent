/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 后端 REST 客户端，探测走 /integrations/mcp/probe)
 * - ./probe (POS: 探测枚举归一化与失败文案 key)
 * - ../deploymentGuard (POS: cloud/sandbox 下阻断 local-only 条目)
 *
 * [OUTPUT]
 * - useConnectivityProbe: 连接前的 MCP 端点连通性探测状态机（空闲/探测中/可达/不可达/云端不支持）
 *
 * [POS]
 * 连接对话框的探测层：只产出状态与本地化错误文案，阻断与否由调用方依据 runProbe 的返回值决定。
 */
'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { apiRequest } from '@/lib/api';
import { shouldBlockCloudLoopbackConnect } from '../deploymentGuard';
import { normalizeProbeReasonCode, normalizeProbeRecommendedMode, probeErrorI18nKey } from './probe';
import type { ProbeRecommendedMode, ProbeStatus } from './probe';

interface ConnectivityProbeInput {
  probeUrl: string | undefined;
  isLocalTauriOnlyEntry: boolean;
  isSandboxMode: boolean;
}

export function useConnectivityProbe({ probeUrl, isLocalTauriOnlyEntry, isSandboxMode }: ConnectivityProbeInput) {
  const t = useTranslations('settings.integrationCatalog.connectDialog');
  const [probeStatus, setProbeStatus] = useState<ProbeStatus>('idle');
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probeRecommendedMode, setProbeRecommendedMode] = useState<ProbeRecommendedMode | null>(null);

  /** Resolves true when the connection may proceed; false leaves the diagnosis in the probe state. */
  const runProbe = useCallback(async () => {
    if (!probeUrl) {
      return true;
    }
    setProbeStatus('probing');
    setProbeError(null);
    setProbeRecommendedMode(null);
    try {
      const res = await apiRequest<{
        status: string;
        error?: string;
        reasonCode?: string;
        recommendedMode?: string;
        shouldBlockConnect?: boolean;
      }>('/integrations/mcp/probe', {
        method: 'POST',
        body: JSON.stringify({ url: probeUrl, timeout: 5 }),
      });
      if (res.status === 'reachable') {
        setProbeStatus('reachable');
        setProbeRecommendedMode(null);
        return true;
      }
      if (res.status === 'cloud_not_supported') {
        const nextMode = normalizeProbeRecommendedMode(res.recommendedMode) ?? 'local_or_tauri';
        setProbeStatus('cloud_not_supported');
        if (res.shouldBlockConnect === true) {
          setProbeError(t('probeCloudLoopbackBlocked'));
          setProbeRecommendedMode(nextMode);
          return false;
        }
        if (
          shouldBlockCloudLoopbackConnect({
            status: res.status,
            isSandboxMode,
            isLocalTauriOnlyEntry,
          })
        ) {
          setProbeError(t('probeCloudLoopbackBlocked'));
          setProbeRecommendedMode(nextMode);
          return false;
        }
        setProbeRecommendedMode(null);
        return true;
      }
      setProbeStatus('unreachable');
      setProbeRecommendedMode(normalizeProbeRecommendedMode(res.recommendedMode));
      const reasonCode = normalizeProbeReasonCode(res.reasonCode);
      const errorKey = probeErrorI18nKey(reasonCode);
      setProbeError(
        errorKey
          ? t(errorKey)
          : t('probeUnknownFailure', {
              default: t('probeUnreachable'),
            }),
      );
      return false;
    } catch {
      setProbeStatus('unreachable');
      setProbeRecommendedMode(null);
      setProbeError(t('probeUnreachable'));
      return false;
    }
  }, [isLocalTauriOnlyEntry, isSandboxMode, probeUrl, t]);

  /** Shows the same diagnosis a cloud_not_supported probe would, without the network round trip. */
  const reportLocalOnlyBlocked = useCallback(() => {
    setProbeStatus('cloud_not_supported');
    setProbeError(t('probeCloudLoopbackBlocked'));
    setProbeRecommendedMode('local_or_tauri');
  }, [t]);

  return { probeStatus, probeError, probeRecommendedMode, runProbe, reportLocalOnlyBlocked };
}

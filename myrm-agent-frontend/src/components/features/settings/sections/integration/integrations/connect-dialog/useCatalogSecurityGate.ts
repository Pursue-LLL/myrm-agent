/**
 * [INPUT]
 * - @/hooks/settings/useMcpSecurityGate (POS: MCP 启用前的安全扫描闸门与扫描摘要)
 * - @/lib/utils/mcp-config::formatMcpGateBlockedMessage (POS: 闸门拒绝原因的用户文案)
 * - @/hooks/shared/useToast (POS: 全局 toast)
 *
 * [OUTPUT]
 * - useCatalogSecurityGate: 目录条目启用前的安全闸门、高风险确认挂起态与通过后的落库（含 hostSerial / keepaliveInterval 继承）
 *
 * [POS]
 * 连接对话框的启用层：连接前统一过安全闸门，通过后落库并通知调用方。
 */
'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { buildLastScanSummary, gateMcpEnable } from '@/hooks/settings/useMcpSecurityGate';
import { formatMcpGateBlockedMessage } from '@/lib/utils/mcp-config';
import type { MCPScanResult, MCPServiceConfig } from '@/store/config/types';

interface CatalogSecurityGateInput {
  entryName: string;
  /** The catalog entry's raw `mcpConfig`; carries optional hostSerial / keepaliveInterval tuning. */
  catalogMcpConfig: Record<string, unknown> | null;
  mcpConfigs: MCPServiceConfig[];
  setMCPConfigs: (configs: MCPServiceConfig[]) => void;
  onConnected: () => void;
}

interface PendingCatalogAck {
  config: MCPServiceConfig;
  scanResult: MCPScanResult;
}

export function useCatalogSecurityGate({
  entryName,
  catalogMcpConfig,
  mcpConfigs,
  setMCPConfigs,
  onConnected,
}: CatalogSecurityGateInput) {
  const t = useTranslations('settings.integrationCatalog.connectDialog');
  const tSettings = useTranslations('settings');
  const [pendingAck, setPendingAck] = useState<PendingCatalogAck | null>(null);

  const persistCatalogConfig = useCallback(
    (config: MCPServiceConfig) => {
      const finalConfig: MCPServiceConfig = {
        ...config,
        hostSerial: catalogMcpConfig?.hostSerial === true ? true : config.hostSerial,
        keepaliveInterval:
          typeof catalogMcpConfig?.keepaliveInterval === 'number'
            ? catalogMcpConfig.keepaliveInterval
            : config.keepaliveInterval,
      };
      // The service may have been added elsewhere while the scan or the acknowledgement was pending.
      const exists = mcpConfigs.some((c) => c.name === finalConfig.name);
      if (!exists) {
        setMCPConfigs([...mcpConfigs, finalConfig]);
      }
      toast({ title: t('connectSuccess', { name: entryName }) });
      onConnected();
    },
    [entryName, catalogMcpConfig, mcpConfigs, onConnected, setMCPConfigs, t],
  );

  /** Saves the config when the gate allows it; otherwise holds it for acknowledgement or reports the refusal. */
  const runCatalogSecurityGate = useCallback(
    async (config: MCPServiceConfig, acknowledgedHighRisks = false) => {
      const gate = await gateMcpEnable(config, { acknowledgedHighRisks });
      if (gate.needsAcknowledgement) {
        setPendingAck({ config, scanResult: gate.scanResult });
        return;
      }
      if (!gate.allowed) {
        toast({
          title: t('connectFailed'),
          description: formatMcpGateBlockedMessage(
            {
              verifyError: gate.verifyError,
              verifyFindings: gate.verifyFindings,
              staticFindings: gate.scanResult.findings,
              fallback: t('connectFailed'),
            },
            tSettings,
          ),
          variant: 'destructive',
        });
        return;
      }
      persistCatalogConfig({
        ...config,
        lastScanSummary: buildLastScanSummary(gate.scanResult),
      });
    },
    [persistCatalogConfig, t, tSettings],
  );

  const confirmAcknowledgement = useCallback(async () => {
    if (!pendingAck) {
      return;
    }
    const { config } = pendingAck;
    setPendingAck(null);
    await runCatalogSecurityGate(config, true);
  }, [pendingAck, runCatalogSecurityGate]);

  const cancelAcknowledgement = useCallback(() => setPendingAck(null), []);

  return { pendingAck, runCatalogSecurityGate, confirmAcknowledgement, cancelAcknowledgement };
}

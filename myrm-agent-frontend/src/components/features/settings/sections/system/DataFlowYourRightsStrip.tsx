/**
 * [INPUT]
 * - @/services/connect::ConnectorStatus (POS: Connect Wizard API client)
 * - @/services/integrations/oauthCredentials::OAuthCredentialItem
 * - @/services/channels/manage::ChannelStatus (POS: Tauri Channel 状态 API)
 *
 * [OUTPUT]
 * - ComplianceEgressSnapshot, export snapshot builders, DataFlowYourRightsStrip
 *
 * [POS]
 * DataFlow 面板「您的数据权利」条：client-side 合规导出与 Memory 设置深链。
 */

'use client';

import { memo, useCallback, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { IconDownload, IconArrowRight } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { toast } from '@/lib/utils/toast';
import { exportMemories } from '@/services/memory/core';
import useConfigStore from '@/store/useConfigStore';
import type { ConnectorStatus } from '@/services/connect';
import type { OAuthCredentialItem } from '@/services/integrations/oauthCredentials';
import type { ChannelStatus } from '@/services/channels/manage';
import type { PrivacyRoutingConfig } from '@/services/config/types';

export interface ComplianceEgressSnapshot {
  providers: Array<{ id: string; name: string; endpoint: string }>;
  mcp: Array<{ name: string; transport: string; endpoint: string }>;
  connectors: Array<{ profileId: string; label: string }>;
  oauthIntegrations: Array<{ issuer: string }>;
  channels: Array<{ instanceId: string; channelType: string; displayName: string }>;
}

export type PrivacyRoutingSnapshot = PrivacyRoutingConfig;

export interface ComplianceExportPrivacySettings {
  enabled: boolean;
  s2_action: string | undefined;
  s3_action: string | undefined;
  deep_scan: boolean | undefined;
  routing: PrivacyRoutingSnapshot | null;
}

export interface ComplianceExportBundle {
  schema: 'myrm.compliance_export.v1';
  exported_at: string;
  memories: {
    version: string | number;
    total_count: number;
    data: unknown;
  };
  privacy_settings: ComplianceExportPrivacySettings;
  egress_snapshot: ComplianceEgressSnapshot;
}

export function redactPrivacyRoutingSnapshot(
  routing: PrivacyRoutingSnapshot | null | undefined,
): PrivacyRoutingSnapshot | null {
  if (!routing) {
    return null;
  }
  if (!routing.localApiKey) {
    return routing;
  }
  return { ...routing, localApiKey: '[REDACTED]' };
}

export function buildComplianceExportBundle(
  memories: { version: string | number; total_count: number; data: unknown },
  privacySettings: ComplianceExportPrivacySettings,
  egressSnapshot: ComplianceEgressSnapshot,
  exportedAt: string = new Date().toISOString(),
): ComplianceExportBundle {
  return {
    schema: 'myrm.compliance_export.v1',
    exported_at: exportedAt,
    memories: {
      version: memories.version,
      total_count: memories.total_count,
      data: memories.data,
    },
    privacy_settings: {
      ...privacySettings,
      routing: redactPrivacyRoutingSnapshot(privacySettings.routing),
    },
    egress_snapshot: egressSnapshot,
  };
}

interface DataFlowYourRightsStripProps {
  egressSnapshot: ComplianceEgressSnapshot;
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export const DataFlowYourRightsStrip = memo(({ egressSnapshot }: DataFlowYourRightsStripProps) => {
  const t = useTranslations('settings.securityPolicy.dataFlow');
  const [exporting, setExporting] = useState(false);

  const privacyEnabled = useConfigStore((s) => s.privacyEnabled);
  const privacyS2Action = useConfigStore((s) => s.privacyS2Action);
  const privacyS3Action = useConfigStore((s) => s.privacyS3Action);
  const privacyDeepScan = useConfigStore((s) => s.privacyDeepScan);
  const privacyRouting = useConfigStore((s) => s.privacyRouting);

  const handleComplianceExport = useCallback(async () => {
    setExporting(true);
    try {
      const memories = await exportMemories();
      const bundle = buildComplianceExportBundle(
        memories,
        {
          enabled: privacyEnabled,
          s2_action: privacyS2Action,
          s3_action: privacyS3Action,
          deep_scan: privacyDeepScan,
          routing: privacyRouting ?? null,
        },
        egressSnapshot,
      );
      const stamp = new Date().toISOString().slice(0, 10);
      downloadJson(`myrm-compliance-export-${stamp}.json`, bundle);
      toast.success(t('rightsExportSuccess'));
    } catch {
      toast.error(t('rightsExportFailed'));
    } finally {
      setExporting(false);
    }
  }, [egressSnapshot, privacyDeepScan, privacyEnabled, privacyRouting, privacyS2Action, privacyS3Action, t]);

  return (
    <div className="rounded-xl border border-border/60 bg-muted/20 p-4.5 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-foreground">{t('yourRightsTitle')}</h4>
        <p className="text-xs text-muted-foreground mt-1">{t('yourRightsDesc')}</p>
      </div>
      <div className="flex flex-col sm:flex-row flex-wrap gap-2">
        <Button type="button" size="sm" variant="default" disabled={exporting} onClick={handleComplianceExport}>
          <IconDownload className="h-3.5 w-3.5 mr-1.5" />
          {exporting ? t('rightsExporting') : t('rightsExportButton')}
        </Button>
        <Button type="button" size="sm" variant="outline" asChild>
          <Link href="/settings/memory">
            {t('rightsManageMemory')}
            <IconArrowRight className="h-3.5 w-3.5 ml-1" />
          </Link>
        </Button>
      </div>
    </div>
  );
});

DataFlowYourRightsStrip.displayName = 'DataFlowYourRightsStrip';

export function buildConnectorEgressSnapshot(connectors: ConnectorStatus[]): ComplianceEgressSnapshot['connectors'] {
  return connectors
    .filter((c) => c.status === 'ready' && c.connected_at)
    .map((c) => ({ profileId: c.profile_id, label: c.label }));
}

export function buildOAuthEgressSnapshot(items: OAuthCredentialItem[]): ComplianceEgressSnapshot['oauthIntegrations'] {
  return items.filter((item) => item.connected).map((item) => ({ issuer: item.issuer }));
}

export function buildChannelEgressSnapshot(channels: ChannelStatus[]): ComplianceEgressSnapshot['channels'] {
  return channels
    .filter((channel) => channel.connected)
    .map((channel) => ({
      instanceId: channel.instanceId,
      channelType: channel.channelType,
      displayName: channel.displayName || channel.name,
    }));
}

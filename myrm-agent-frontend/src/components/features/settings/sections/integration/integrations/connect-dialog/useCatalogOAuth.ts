/**
 * [INPUT]
 * - @/lib/api::apiRequest / BACKEND_BASE_URL (POS: 后端 REST 客户端，OAuth 起始与状态轮询)
 * - @/hooks/shared/useToast (POS: 全局 toast)
 * - ../catalog-types (POS: 目录条目 mcpConfig 的 OAuth 类型视图)
 *
 * [OUTPUT]
 * - useCatalogOAuth: 目录条目的 OAuth 连接流程：起始授权、系统浏览器打开授权页、轮询授权结果并交给安全闸门
 *
 * [POS]
 * 连接对话框的 OAuth 层：轮询句柄随组件卸载清理；授权成功后的启用/落库由注入的 runCatalogSecurityGate 负责。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { apiRequest, BACKEND_BASE_URL } from '@/lib/api';
import type { MCPServiceConfig } from '@/store/config/types';
import type { CatalogEntry, CatalogMcpDialogConfig } from '../catalog-types';

const OAUTH_POLL_INTERVAL_MS = 2000;

interface CatalogOAuthInput {
  entry: CatalogEntry;
  runCatalogSecurityGate: (config: MCPServiceConfig) => Promise<boolean>;
}

export function useCatalogOAuth({ entry, runCatalogSecurityGate }: CatalogOAuthInput) {
  const t = useTranslations('settings.integrationCatalog.connectDialog');
  const [oauthPolling, setOauthPolling] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const startOAuthConnect = useCallback(async () => {
    setOauthPolling(true);
    try {
      const mcpCfg = entry.mcpConfig as unknown as CatalogMcpDialogConfig | null;
      const oauthCfg = mcpCfg?.oauth;
      if (!mcpCfg || !oauthCfg) {
        toast({ title: t('connectFailed'), description: 'Missing OAuth config', variant: 'destructive' });
        setOauthPolling(false);
        return;
      }

      // 1. Start OAuth flow
      const startRes = await apiRequest<{ authorization_url: string; state: string }>('/integrations/mcp/oauth/start', {
        method: 'POST',
        body: JSON.stringify({
          server_name: mcpCfg.name,
          authorization_endpoint: oauthCfg.authorization_endpoint,
          token_endpoint: oauthCfg.token_endpoint,
          client_id: oauthCfg.client_id,
          client_secret: oauthCfg.client_secret,
          scope: oauthCfg.scope,
          redirect_uri: `${BACKEND_BASE_URL || window.location.origin}/api/v1/integrations/mcp/oauth/callback`,
        }),
      });

      // 2. Open authorization URL
      if ('__TAURI__' in window) {
        const { open } = await import('@tauri-apps/plugin-shell');
        await open(startRes.authorization_url);
      } else {
        window.open(startRes.authorization_url, '_blank');
      }

      // 3. Poll for status
      pollIntervalRef.current = setInterval(async () => {
        try {
          const statusRes = await apiRequest<{ status: string }>(`/integrations/mcp/oauth/status/${startRes.state}`, {
            silent: true,
          });
          if (statusRes.status === 'success') {
            stopPolling();
            const newConfig: MCPServiceConfig = {
              name: mcpCfg.name,
              type: mcpCfg.type,
              url: mcpCfg.url || '',
              command: mcpCfg.command || '',
              args: mcpCfg.args || [],
              description: mcpCfg.description || '',
              enabled: true,
              extra_params: null,
            };
            setOauthPolling(false);
            await runCatalogSecurityGate(newConfig);
          } else if (statusRes.status === 'expired_or_invalid') {
            stopPolling();
            setOauthPolling(false);
            toast({ title: t('connectFailed'), description: 'OAuth session expired', variant: 'destructive' });
          }
        } catch {
          // Ignore polling errors
        }
      }, OAUTH_POLL_INTERVAL_MS);
    } catch (e) {
      setOauthPolling(false);
      toast({ title: t('connectFailed'), description: String(e), variant: 'destructive' });
    }
  }, [entry.mcpConfig, runCatalogSecurityGate, stopPolling, t]);

  return { oauthPolling, startOAuthConnect };
}

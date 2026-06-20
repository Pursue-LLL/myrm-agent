import { useState, useCallback, useEffect, useRef } from 'react';
import {
  IconLoader,
  IconPencil,
  IconPlus,
  IconShield,
  IconTrash,
  IconUpload,
} from '@/components/features/icons/PremiumIcons';
import { useTranslations } from 'next-intl';
import { Switch } from '@/components/primitives/switch';
import { Button } from '@/components/primitives/button';
import { MCPServiceConfig } from '@/store/useConfigStore';
import {
  startMCPOAuth,
  checkMCPOAuthStateStatus,
  getMCPOAuthStatus,
  disconnectMCPOAuth,
  MCPOAuthStatusMap,
} from '@/services/llm-config';
import { BACKEND_BASE_URL } from '@/lib/api';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { useToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils/classnameUtils';

function severityBadgeClass(severity: string | null | undefined): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
    case 'high':
      return 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400';
    case 'medium':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400';
    case 'low':
      return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

interface MCPConfigListProps {
  configs: MCPServiceConfig[];
  mcpStatus: Record<string, { available: boolean; pending?: boolean; latency?: number }>;
  togglingIndex?: number | null;
  onAddConfig: () => void;
  onEditConfig: (index: number) => void;
  onToggleConfig: (index: number) => void;
  onDeleteConfirm: (index: number) => void;
  onShowImport: () => void;
}

/**
 * MCP配置列表组件
 *
 * 显示所有MCP服务配置，支持：
 * - 启用/禁用切换
 * - 在线状态显示（带延迟）
 * - 编辑和删除操作
 * - 添加新配置和JSON导入
 *
 * @param props MCPConfigListProps
 */
export function MCPConfigList({
  configs,
  mcpStatus,
  togglingIndex = null,
  onAddConfig,
  onEditConfig,
  onToggleConfig,
  onDeleteConfirm,
  onShowImport,
}: MCPConfigListProps) {
  const t = useTranslations('settings');
  const { toast } = useToast();
  const [oauthStatus, setOauthStatus] = useState<MCPOAuthStatusMap>({});
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const hasOAuthConfigs = configs.some((c) => c.oauth?.clientId);
    if (!hasOAuthConfigs) return;
    getMCPOAuthStatus()
      .then(setOauthStatus)
      .catch(() => {});
  }, [configs]);

  const handleOAuthAuthorize = useCallback(
    async (config: MCPServiceConfig) => {
      if (!config.oauth?.clientId) return;
      setOauthLoading(config.name);
      try {
        const callbackBase = BACKEND_BASE_URL || window.location.origin;
        const backendCallbackUrl = `${callbackBase}/api/v1/integrations/mcp/oauth/callback`;
        const resp = await startMCPOAuth({
          server_name: config.name,
          authorization_endpoint: config.oauth.authorizationEndpoint,
          token_endpoint: config.oauth.tokenEndpoint,
          client_id: config.oauth.clientId,
          client_secret: config.oauth.clientSecret,
          scope: config.oauth.scope,
          redirect_uri: backendCallbackUrl,
        });

        if (isTauriRuntime()) {
          const { open } = await import('@tauri-apps/plugin-shell');
          await open(resp.authorization_url);
        } else {
          window.open(resp.authorization_url, '_blank', 'width=600,height=700');
        }

        const POLL_INTERVAL_MS = 2000;
        const POLL_TIMEOUT_MS = 5 * 60 * 1000;
        const startTime = Date.now();

        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        pollTimerRef.current = setInterval(async () => {
          if (Date.now() - startTime > POLL_TIMEOUT_MS) {
            clearInterval(pollTimerRef.current!);
            pollTimerRef.current = null;
            setOauthLoading(null);
            toast({ title: t('mcpOAuthFailed') || 'OAuth Failed', variant: 'destructive' });
            return;
          }
          try {
            const statusRes = await checkMCPOAuthStateStatus(resp.state);
            if (statusRes.status === 'success') {
              clearInterval(pollTimerRef.current!);
              pollTimerRef.current = null;
              setOauthStatus((prev) => ({
                ...prev,
                [config.name]: { connected: true, expired: false, scope: config.oauth?.scope || null },
              }));
              setOauthLoading(null);
              toast({ title: t('mcpOAuthSuccess') || 'OAuth Connected' });
            } else if (statusRes.status === 'expired_or_invalid') {
              clearInterval(pollTimerRef.current!);
              pollTimerRef.current = null;
              setOauthLoading(null);
              toast({ title: t('mcpOAuthFailed') || 'OAuth Failed', variant: 'destructive' });
            }
          } catch {
            // transient polling errors, continue
          }
        }, POLL_INTERVAL_MS);
      } catch {
        toast({ title: t('mcpOAuthFailed') || 'OAuth Failed', variant: 'destructive' });
        setOauthLoading(null);
      }
    },
    [t, toast],
  );

  const handleOAuthDisconnect = useCallback(
    async (serverName: string) => {
      try {
        await disconnectMCPOAuth(serverName);
        setOauthStatus((prev) => {
          const next = { ...prev };
          delete next[serverName];
          return next;
        });
        toast({ title: t('mcpOAuthDisconnected') || 'OAuth Disconnected' });
      } catch {
        toast({ title: t('mcpOAuthDisconnectFailed') || 'Disconnect Failed', variant: 'destructive' });
      }
    },
    [t, toast],
  );

  return (
    <div className="flex flex-col space-y-4">
      {/* 标题和操作按钮 */}
      <div className="flex items-center justify-between">
        <h3 className="text-md font-medium text-black/80 dark:text-white/80">{t('mcpServiceConfig')}</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={onShowImport}
            className="flex items-center space-x-2 px-3 py-1.5 bg-secondary border border-border text-foreground rounded-lg hover:bg-muted transition-colors text-sm"
          >
            <IconUpload className="w-4 h-4" />
            <span>{t('mcpImportJson')}</span>
          </button>
          <Button type="button" size="sm" onClick={onAddConfig} className="gap-2 rounded-lg bg-primary text-white hover:bg-primary/90">
            <IconPlus className="w-4 h-4" />
            <span>{t('mcpAddService')}</span>
          </Button>
        </div>
      </div>

      {/* 配置列表 */}
      {configs.length > 0 && (
        <div className="space-y-3">
          {configs.map((config, index) => {
            const status = mcpStatus[config.name];
            const oauth = oauthStatus[config.name];
            const hasOAuthConfig = !!config.oauth?.clientId;
            const scanSeverity = config.lastScanSummary?.maxSeverity;
            const isToggling = togglingIndex === index;
            return (
              <div
                key={index}
                onClick={() => onEditConfig(index)}
                className="flex items-center justify-between p-3 bg-secondary rounded-lg border border-border cursor-pointer hover:bg-muted/50 transition-colors group"
              >
                <div className="flex items-center space-x-3">
                  <div
                    className="flex items-center gap-1.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Switch
                      checked={config.enabled}
                      disabled={isToggling}
                      onCheckedChange={() => onToggleConfig(index)}
                    />
                    {isToggling ? (
                      <IconLoader className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                    ) : null}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-black/90 dark:text-white/90 flex items-center gap-1">
                      {config.name}
                      <span
                        className={
                          status?.pending
                            ? 'inline-block w-2 h-2 rounded-full bg-muted-foreground/40 animate-pulse'
                            : status?.available
                              ? 'inline-block w-2 h-2 rounded-full bg-green-500'
                              : 'inline-block w-2 h-2 rounded-full bg-red-500'
                        }
                      />
                      {hasOAuthConfig && oauth?.connected && !oauth.expired && (
                        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                          <IconShield className="w-2.5 h-2.5" />
                          OAuth
                        </span>
                      )}
                      {hasOAuthConfig && oauth?.connected && oauth.expired && (
                        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                          <IconShield className="w-2.5 h-2.5" />
                          {t('mcpOAuthExpired') || 'Expired'}
                        </span>
                      )}
                      {scanSeverity && (
                        <span
                          className={cn(
                            'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase',
                            severityBadgeClass(scanSeverity),
                          )}
                        >
                          <IconShield className="w-2.5 h-2.5" />
                          {scanSeverity}
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-black/60 dark:text-white/60">
                      {config.type} - {config.description}
                      {status?.pending && (
                        <span className="ml-2 text-muted-foreground">{t('mcpServiceStatusChecking')}</span>
                      )}
                      {!status?.pending && status?.available && typeof status.latency === 'number' && (
                        <span className="ml-2 text-green-600 dark:text-green-400">
                          {t('mcpServiceStatusAvailable', { latency: status.latency })}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  {hasOAuthConfig && (
                    <div onClick={(e) => e.stopPropagation()}>
                      {oauth?.connected && !oauth.expired ? (
                        <button
                          onClick={() => handleOAuthDisconnect(config.name)}
                          className="px-2 py-1 text-xs text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded transition-colors"
                        >
                          {t('mcpOAuthDisconnect') || 'Disconnect'}
                        </button>
                      ) : (
                        <button
                          onClick={() => handleOAuthAuthorize(config)}
                          disabled={oauthLoading === config.name}
                          className="px-2 py-1 text-xs text-primary hover:text-primary/80 hover:bg-primary/5 rounded transition-colors disabled:opacity-50"
                        >
                          {oauthLoading === config.name
                            ? t('mcpOAuthAuthorizing') || 'Authorizing...'
                            : t('mcpOAuthAuthorize') || 'Authorize'}
                        </button>
                      )}
                    </div>
                  )}
                  <span className="p-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <IconPencil className="w-3.5 h-3.5 text-black/50 dark:text-white/50" />
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteConfirm(index);
                    }}
                    className="p-1.5 hover:bg-muted dark:hover:bg-muted rounded transition-colors"
                    title={t('mcpConfirmDelete')}
                  >
                    <IconTrash className="w-3.5 h-3.5 text-red-500" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

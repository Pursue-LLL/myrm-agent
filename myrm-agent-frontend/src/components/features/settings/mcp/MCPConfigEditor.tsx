import { useState, useCallback } from 'react';
import {
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconFileText,
  IconGlobe,
  IconKey,
  IconLoader,
  IconLock,
  IconPencil,
  IconPlus,
  IconShield,
  IconTrash,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { getMcpFindingDescription, getMcpFindingRecommendation } from '@/lib/utils/mcpScanFindingText';
import { Switch } from '@/components/primitives/switch';
import { InputField } from '../FormFields';
import { MCPServiceConfig, MCPOAuthSettings } from '@/store/useConfigStore';
import { PendingDescriptionChoice } from '@/hooks/useMCPConfig';
import type { MCPScanFinding } from '@/store/config/types';
import JsonEditor from '../JsonEditor';
import OptionSelect from '../OptionSelect';

interface MCPConfigEditorProps {
  show: boolean;
  editingIndex: number | null;
  formData: MCPServiceConfig;
  rawArgsInput: string;
  errors: Record<string, string>;
  isValidating: boolean;
  validationSuccess: boolean;
  validationError: string;
  validationLatency: number | null;
  scanFindings: MCPScanFinding[];
  isLiveScanning: boolean;
  connectionTypeOptions: Array<{ value: string; label: string; description: string }>;
  pendingDescriptionChoice: PendingDescriptionChoice | null;
  onFormDataChange: (data: MCPServiceConfig) => void;
  onRawArgsInputChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onConfirmDescription: (desc: string) => void;
  onCancelDescriptionChoice: () => void;
}

/**
 * MCP 配置编辑弹窗
 *
 * 验证通过后若 MCP 返回了 instructions 且与用户填写的描述不同，
 * 会弹出 DescriptionChoiceDialog 让用户二选一。
 */
export function MCPConfigEditor({
  show,
  editingIndex,
  formData,
  rawArgsInput,
  errors,
  isValidating,
  validationSuccess,
  validationError,
  validationLatency,
  scanFindings,
  isLiveScanning,
  connectionTypeOptions,
  pendingDescriptionChoice,
  onFormDataChange,
  onRawArgsInputChange,
  onSave,
  onCancel,
  onConfirmDescription,
  onCancelDescriptionChoice,
}: MCPConfigEditorProps) {
  const t = useTranslations('settings');

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-background rounded-2xl max-w-2xl w-full mx-4 shadow-xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* 弹窗头部 */}
        <div className="flex items-center justify-between p-5 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              {editingIndex !== null ? (
                <IconPencil className="w-[18px] h-[18px] text-primary" />
              ) : (
                <IconPlus className="w-[18px] h-[18px] text-primary" />
              )}
            </div>
            <h3 className="text-lg font-semibold text-foreground">
              {editingIndex !== null ? t('mcpEditService') : t('mcpAddService')}
            </h3>
          </div>
          <button onClick={onCancel} className="p-2 rounded-lg hover:bg-muted transition-colors">
            <IconX className="w-[18px] h-[18px] text-muted-foreground" />
          </button>
        </div>

        {/* 弹窗内容 - 可滚动 */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <InputField
              label={t('mcpServiceName')}
              value={formData.name}
              onChange={(e) => onFormDataChange({ ...formData, name: e.target.value })}
              error={errors.name}
              placeholder={t('mcpServiceNamePlaceholder')}
            />

            <div className="flex flex-col space-y-1">
              <label className="text-black/70 dark:text-white/70 text-sm">{t('mcpConnectionType')}</label>
              <OptionSelect
                value={formData.type}
                onChange={(value) => {
                  const nextType = value as 'sse' | 'stdio' | 'streamable_http';
                  onFormDataChange({
                    ...formData,
                    type: nextType,
                    keepaliveInterval: nextType === 'stdio' ? null : (formData.keepaliveInterval ?? null),
                  });
                }}
                options={connectionTypeOptions}
              />
            </div>
          </div>

          {(formData.type === 'sse' || formData.type === 'streamable_http') && (
            <InputField
              label="URL"
              value={formData.url || ''}
              onChange={(e) => onFormDataChange({ ...formData, url: e.target.value })}
              error={errors.url}
              placeholder={t('mcpUrlPlaceholder')}
            />
          )}

          {formData.type === 'stdio' && (
            <>
              <InputField
                label={t('mcpCommand')}
                value={formData.command || ''}
                onChange={(e) => onFormDataChange({ ...formData, command: e.target.value })}
                error={errors.command}
                placeholder={t('mcpCommandPlaceholder')}
              />

              <div className="flex flex-col space-y-2">
                <label className="text-black/70 dark:text-white/70 text-sm">{t('mcpArgs')}</label>
                <div className="text-xs text-black/60 dark:text-white/60 space-y-1">
                  <p>{t('mcpArgsHint')}</p>
                </div>
                <textarea
                  value={rawArgsInput}
                  onChange={(e) => onRawArgsInputChange(e.target.value)}
                  className={cn(
                    'w-full px-3 py-2 border border-border rounded-lg text-sm resize-none font-mono',
                    'bg-muted/30 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                  )}
                  rows={4}
                  placeholder={`["-y", "mcp-server-example"]`}
                />
                {/* 参数预览 */}
                {rawArgsInput.trim() && (
                  <div className="p-2 bg-muted/50 rounded-lg border border-border">
                    <p className="text-xs text-black/60 dark:text-white/60 mb-1">{t('mcpArgsPreview')}</p>
                    <div className="text-xs font-mono text-black/80 dark:text-white/80">
                      {(() => {
                        try {
                          const trimmedInput = rawArgsInput.trim();
                          let previewArgs: string[] = [];

                          if (trimmedInput.startsWith('[') && trimmedInput.endsWith(']')) {
                            const parsedArgs = JSON.parse(trimmedInput);
                            if (Array.isArray(parsedArgs)) {
                              previewArgs = parsedArgs.map((arg) => String(arg)).filter((arg) => arg.trim() !== '');
                            } else {
                              return <span className="text-red-500">{t('mcpArgsErrorNotArray')}</span>;
                            }
                          } else {
                            previewArgs = rawArgsInput.split('\n').filter((arg) => arg.trim() !== '');
                          }

                          return (
                            <span className="text-green-600 dark:text-green-400">
                              [{previewArgs.map((arg) => `"${arg}"`).join(', ')}]
                            </span>
                          );
                        } catch (error) {
                          return (
                            <span className="text-red-500">
                              {t('mcpArgsErrorParse')}: {error instanceof Error ? error.message : ''}
                            </span>
                          );
                        }
                      })()}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          <InputField
            label={t('mcpDescription')}
            value={formData.description}
            onChange={(e) => onFormDataChange({ ...formData, description: e.target.value })}
            error={errors.description}
            placeholder={t('mcpDescriptionPlaceholder')}
          />

          {/* 额外参数配置 */}
          <div className="w-full overflow-x-auto">
            <JsonEditor
              label={t('mcpExtraParams')}
              value={formData.extra_params || {}}
              onChange={(value) => onFormDataChange({ ...formData, extra_params: value })}
              tooltip={t('mcpExtraParamsTooltip')}
              placeholder={`{\n  "env": {\n    "KEY": "VALUE"\n  },\n  "cwd": "/path/to/working/directory"\n}`}
            />
          </div>

          {/* 超时配置 */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <InputField
              label={t('mcpConnectTimeout')}
              type="number"
              value={formData.connectTimeout ?? ''}
              onChange={(e) =>
                onFormDataChange({
                  ...formData,
                  connectTimeout: e.target.value ? Number(e.target.value) : null,
                })
              }
              placeholder="15"
            />
            <InputField
              label={t('mcpExecuteTimeout')}
              type="number"
              value={formData.executeTimeout ?? ''}
              onChange={(e) =>
                onFormDataChange({
                  ...formData,
                  executeTimeout: e.target.value ? Number(e.target.value) : null,
                })
              }
              placeholder="120"
            />
            {(formData.type === 'sse' || formData.type === 'streamable_http') && (
              <InputField
                label={t('mcpKeepaliveInterval')}
                type="number"
                value={formData.keepaliveInterval ?? ''}
                error={errors.keepaliveInterval}
                onChange={(e) =>
                  onFormDataChange({
                    ...formData,
                    keepaliveInterval: e.target.value ? Number(e.target.value) : null,
                  })
                }
                placeholder="180"
              />
            )}
          </div>

          {/* HTTP Headers (HTTP transports only) */}
          {(formData.type === 'sse' || formData.type === 'streamable_http') && (
            <HeadersSection formData={formData} onFormDataChange={onFormDataChange} />
          )}

          {/* TLS / mTLS (HTTP transports only) */}
          {(formData.type === 'sse' || formData.type === 'streamable_http') && (
            <TLSSection formData={formData} onFormDataChange={onFormDataChange} />
          )}

          {/* OAuth 2.0 (HTTP transports only) */}
          {(formData.type === 'sse' || formData.type === 'streamable_http') && (
            <OAuthSection formData={formData} onFormDataChange={onFormDataChange} />
          )}

          <div className="flex items-start justify-between gap-3 rounded-lg border border-border p-3">
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">{t('mcpStateAwareSerialMode')}</p>
              <p className="text-xs text-muted-foreground">
                {t('mcpStateAwareSerialModeHint')}
              </p>
            </div>
            <Switch
              checked={Boolean(formData.hostSerial)}
              onCheckedChange={(checked) => onFormDataChange({ ...formData, hostSerial: checked })}
            />
          </div>

          <div className="flex items-center space-x-3">
            <Switch
              checked={formData.enabled}
              onCheckedChange={(checked) => onFormDataChange({ ...formData, enabled: checked })}
            />
            <span className="text-sm text-black/70 dark:text-white/70">{t('mcpEnableService')}</span>
          </div>

          {(isLiveScanning || scanFindings.length > 0) && (
            <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg space-y-2">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-300 flex items-center gap-2">
                {isLiveScanning ? (
                  <IconLoader className="w-4 h-4 animate-spin" />
                ) : (
                  <IconShield className="w-4 h-4" />
                )}
                {isLiveScanning ? t('mcpScanRunning') : t('mcpScanFindingsTitle')}
              </p>
              {!isLiveScanning && (
                <ul className="text-xs text-amber-700 dark:text-amber-400 space-y-2">
                  {scanFindings.slice(0, 5).map((finding, idx) => (
                    <li key={`${finding.field}-${idx}`} className="space-y-0.5">
                      <div>
                        [{finding.severity}] {getMcpFindingDescription(finding, t)}
                      </div>
                      {finding.recommendation ? (
                        <div className="text-muted-foreground">
                          {getMcpFindingRecommendation(finding, t)}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {validationError && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-600 dark:text-red-400">{validationError}</p>
            </div>
          )}
        </div>

        {/* 弹窗底部 */}
        <div className="flex justify-end gap-3 p-5 border-t border-border bg-muted/20 shrink-0">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors"
          >
            {t('mcpCancel')}
          </button>
          <button
            onClick={onSave}
            disabled={isValidating}
            className={cn(
              'flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              validationSuccess ? 'bg-green-500 text-white' : 'bg-primary text-white hover:bg-primary/90',
              isValidating && 'opacity-50 cursor-not-allowed',
            )}
          >
            {isValidating ? (
              <IconLoader className="w-4 h-4 animate-spin" />
            ) : validationSuccess ? (
              <IconCheck className="w-4 h-4" />
            ) : null}
            <span>
              {isValidating
                ? t('mcpValidating')
                : validationSuccess
                  ? `${t('mcpSaveSuccess')}${validationLatency ? ` (${validationLatency}ms)` : ''}`
                  : t('mcpSaveConfig')}
            </span>
          </button>
        </div>
      </div>

      {/* 描述选择对话框 */}
      {pendingDescriptionChoice && (
        <DescriptionChoiceDialog
          userDescription={pendingDescriptionChoice.finalFormData.description}
          serverInstructions={pendingDescriptionChoice.serverInstructions}
          onConfirm={onConfirmDescription}
          onCancel={onCancelDescriptionChoice}
        />
      )}
    </div>
  );
}

function HeadersSection({
  formData,
  onFormDataChange,
}: {
  formData: MCPServiceConfig;
  onFormDataChange: (data: MCPServiceConfig) => void;
}) {
  const t = useTranslations('settings');
  const headers = formData.headers || {};
  const entries = Object.entries(headers);
  const hasHeaders = entries.length > 0;
  const [expanded, setExpanded] = useState(hasHeaders);

  const updateHeaders = (newHeaders: Record<string, string>) => {
    const cleaned = Object.keys(newHeaders).length > 0 ? newHeaders : null;
    onFormDataChange({ ...formData, headers: cleaned });
  };

  const addHeader = () => {
    let newKey = '';
    let suffix = 1;
    while (newKey in headers) {
      newKey = `Header-${suffix++}`;
    }
    updateHeaders({ ...headers, [newKey]: '' });
    if (!expanded) setExpanded(true);
  };

  const removeHeader = (key: string) => {
    const next = { ...headers };
    delete next[key];
    updateHeaders(next);
  };

  const renameKey = (oldKey: string, newKey: string, idx: number) => {
    const rebuilt: Record<string, string> = {};
    entries.forEach(([k, v], i) => {
      rebuilt[i === idx ? newKey : k] = v;
    });
    updateHeaders(rebuilt);
  };

  const updateValue = (key: string, value: string) => {
    updateHeaders({ ...headers, [key]: value });
  };

  const isSecretRef = (v: string) => /\{\{secret:/.test(v);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 p-3 text-sm font-medium text-foreground/80 hover:bg-muted/40 transition-colors"
      >
        {expanded ? (
          <IconChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <IconChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
        )}
        <IconGlobe className="w-3.5 h-3.5 text-muted-foreground" />
        <span>{t('mcpHeadersSection')}</span>
        {hasHeaders && <span className="ml-auto text-xs text-primary font-normal">{t('mcpHeadersConfigured')}</span>}
      </button>
      {expanded && (
        <div className="p-3 pt-0 space-y-2">
          {entries.map(([key, value], idx) => (
            <div key={idx} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-1.5 sm:gap-2">
              <input
                type="text"
                value={key}
                onChange={(e) => renameKey(key, e.target.value, idx)}
                className={cn(
                  'flex-1 min-w-0 px-2.5 py-1.5 text-sm border border-border rounded-lg',
                  'bg-muted/30 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                )}
                placeholder={t('mcpHeaderKeyPlaceholder')}
              />
              <div className="flex items-center gap-1.5 sm:gap-2 flex-1 min-w-0">
                <div className="relative flex-1 min-w-0">
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => updateValue(key, e.target.value)}
                    className={cn(
                      'w-full px-2.5 py-1.5 text-sm border border-border rounded-lg font-mono',
                      'bg-muted/30 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                      isSecretRef(value) && 'pr-7',
                    )}
                    placeholder={t('mcpHeaderValuePlaceholder')}
                  />
                  {isSecretRef(value) && (
                    <IconKey className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-amber-500" />
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeHeader(key)}
                  className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 text-muted-foreground hover:text-red-500 transition-colors shrink-0"
                >
                  <IconTrash className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={addHeader}
            className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 transition-colors py-1"
          >
            <IconPlus className="w-3 h-3" />
            <span>{t('mcpHeaderAdd')}</span>
          </button>
          <p className="text-xs text-muted-foreground">{t('mcpHeadersHint')}</p>
        </div>
      )}
    </div>
  );
}

function TLSSection({
  formData,
  onFormDataChange,
}: {
  formData: MCPServiceConfig;
  onFormDataChange: (data: MCPServiceConfig) => void;
}) {
  const t = useTranslations('settings');
  const hasTlsValues =
    !!(formData.sslVerify !== undefined && formData.sslVerify !== null) ||
    !!formData.clientCert ||
    !!formData.clientKey ||
    !!formData.clientKeyPassword;
  const [expanded, setExpanded] = useState(hasTlsValues);

  const sslVerifyDisplay = (() => {
    if (formData.sslVerify === false) return 'false';
    if (typeof formData.sslVerify === 'string') return formData.sslVerify;
    return '';
  })();

  const handleSslVerifyChange = (value: string) => {
    const trimmed = value.trim();
    if (trimmed === '' || trimmed === 'true') {
      onFormDataChange({ ...formData, sslVerify: null });
    } else if (trimmed === 'false') {
      onFormDataChange({ ...formData, sslVerify: false });
    } else {
      onFormDataChange({ ...formData, sslVerify: trimmed });
    }
  };

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 p-3 text-sm font-medium text-foreground/80 hover:bg-muted/40 transition-colors"
      >
        {expanded ? (
          <IconChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <IconChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
        )}
        <IconLock className="w-3.5 h-3.5 text-muted-foreground" />
        <span>{t('mcpTlsSection')}</span>
        {hasTlsValues && <span className="ml-auto text-xs text-primary font-normal">{t('mcpTlsConfigured')}</span>}
      </button>
      {expanded && (
        <div className="p-3 pt-0 space-y-3">
          <InputField
            label={t('mcpSslVerify')}
            value={sslVerifyDisplay}
            onChange={(e) => handleSslVerifyChange(e.target.value)}
            placeholder={t('mcpSslVerifyPlaceholder')}
          />
          {formData.sslVerify === false && (
            <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50">
              <IconLock className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-700 dark:text-amber-300">{t('mcpSslVerifyWarning')}</p>
            </div>
          )}
          <InputField
            label={t('mcpClientCert')}
            value={formData.clientCert || ''}
            onChange={(e) => onFormDataChange({ ...formData, clientCert: e.target.value || null })}
            placeholder={t('mcpClientCertPlaceholder')}
          />
          <InputField
            label={t('mcpClientKey')}
            value={formData.clientKey || ''}
            onChange={(e) => onFormDataChange({ ...formData, clientKey: e.target.value || null })}
            placeholder={t('mcpClientKeyPlaceholder')}
          />
          <InputField
            label={t('mcpClientKeyPassword')}
            isPassword
            value={formData.clientKeyPassword || ''}
            onChange={(e) => onFormDataChange({ ...formData, clientKeyPassword: e.target.value || null })}
            placeholder={t('mcpClientKeyPasswordPlaceholder')}
          />
          <p className="text-xs text-muted-foreground">{t('mcpTlsHint')}</p>
        </div>
      )}
    </div>
  );
}

function OAuthSection({
  formData,
  onFormDataChange,
}: {
  formData: MCPServiceConfig;
  onFormDataChange: (data: MCPServiceConfig) => void;
}) {
  const t = useTranslations('settings');
  const oauth = formData.oauth;
  const hasOAuth = !!oauth?.clientId;
  const [expanded, setExpanded] = useState(hasOAuth);

  const updateOAuth = useCallback(
    (updates: Partial<MCPOAuthSettings>) => {
      const current: MCPOAuthSettings = oauth || {
        authorizationEndpoint: '',
        tokenEndpoint: '',
        clientId: '',
      };
      onFormDataChange({ ...formData, oauth: { ...current, ...updates } });
    },
    [formData, oauth, onFormDataChange],
  );

  const clearOAuth = useCallback(() => {
    onFormDataChange({ ...formData, oauth: null });
  }, [formData, onFormDataChange]);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 p-3 text-sm font-medium text-foreground/80 hover:bg-muted/40 transition-colors"
      >
        {expanded ? (
          <IconChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <IconChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
        )}
        <IconShield className="w-3.5 h-3.5 text-muted-foreground" />
        <span>OAuth 2.0</span>
        {hasOAuth && <span className="ml-auto text-xs text-primary font-normal">{t('mcpOAuthConfigured')}</span>}
      </button>
      {expanded && (
        <div className="p-3 pt-0 space-y-3">
          <InputField
            label={t('mcpOAuthClientId') || 'Client ID'}
            value={oauth?.clientId || ''}
            onChange={(e) => updateOAuth({ clientId: e.target.value })}
            placeholder="your-app-client-id"
          />
          <InputField
            label={t('mcpOAuthClientSecret') || 'Client Secret'}
            isPassword
            value={oauth?.clientSecret || ''}
            onChange={(e) => updateOAuth({ clientSecret: e.target.value || undefined })}
            placeholder={t('mcpOAuthClientSecretPlaceholder') || 'Optional for public clients'}
          />
          <InputField
            label={t('mcpOAuthAuthEndpoint') || 'Authorization Endpoint'}
            value={oauth?.authorizationEndpoint || ''}
            onChange={(e) => updateOAuth({ authorizationEndpoint: e.target.value })}
            placeholder="https://provider.com/oauth/authorize"
          />
          <InputField
            label={t('mcpOAuthTokenEndpoint') || 'Token Endpoint'}
            value={oauth?.tokenEndpoint || ''}
            onChange={(e) => updateOAuth({ tokenEndpoint: e.target.value })}
            placeholder="https://provider.com/oauth/token"
          />
          <InputField
            label={t('mcpOAuthScope') || 'Scope'}
            value={oauth?.scope || ''}
            onChange={(e) => updateOAuth({ scope: e.target.value || undefined })}
            placeholder="read write"
          />
          {hasOAuth && (
            <button
              type="button"
              onClick={clearOAuth}
              className="text-xs text-red-500 hover:text-red-600 transition-colors"
            >
              {t('mcpOAuthClear') || 'Clear OAuth configuration'}
            </button>
          )}
          <p className="text-xs text-muted-foreground">
            {t('mcpOAuthHint') ||
              'Configure OAuth 2.0 + PKCE for remote MCP servers requiring authorization. After saving, click "Authorize" in the server list to complete the OAuth flow.'}
          </p>
        </div>
      )}
    </div>
  );
}

function DescriptionChoiceDialog({
  userDescription,
  serverInstructions,
  onConfirm,
  onCancel,
}: {
  userDescription: string;
  serverInstructions: string;
  onConfirm: (desc: string) => void;
  onCancel: () => void;
}) {
  const t = useTranslations('settings');

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60] p-4">
      <div className="bg-white dark:bg-background rounded-2xl max-w-lg w-full shadow-xl overflow-hidden">
        <div className="p-5 border-b border-border">
          <h3 className="text-base font-semibold text-foreground">{t('mcpChooseDescription')}</h3>
          <p className="text-xs text-muted-foreground mt-1">{t('mcpChooseDescriptionHint')}</p>
        </div>

        <div className="p-5 space-y-3">
          <button
            onClick={() => onConfirm(serverInstructions)}
            className={cn(
              'w-full text-left p-3.5 rounded-xl border-2 transition-all',
              'hover:border-primary/60 hover:bg-primary/5',
              'border-border bg-card',
            )}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <IconFileText className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">
                {t('mcpOfficialDescription')}
              </span>
            </div>
            <p className="text-sm text-foreground/80 line-clamp-4">{serverInstructions}</p>
          </button>

          <button
            onClick={() => onConfirm(userDescription)}
            className={cn(
              'w-full text-left p-3.5 rounded-xl border-2 transition-all',
              'hover:border-primary/60 hover:bg-primary/5',
              'border-border bg-card',
            )}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <IconPencil className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                {t('mcpCustomDescription')}
              </span>
            </div>
            <p className="text-sm text-foreground/80 line-clamp-4">{userDescription}</p>
          </button>
        </div>

        <div className="flex justify-end p-4 border-t border-border bg-muted/20">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors"
          >
            {t('mcpCancel')}
          </button>
        </div>
      </div>
    </div>
  );
}

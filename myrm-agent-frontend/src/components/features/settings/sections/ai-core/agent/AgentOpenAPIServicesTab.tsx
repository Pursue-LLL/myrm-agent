'use client';

import { useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import {
  type OpenAPIServiceConfig,
  type OpenAPIAuthType,
  type OpenAPIAuthConfig,
  type ParseSpecResponse,
  parseOpenAPISpec,
  getSaaSPresets,
  type SaaSPreset,
} from '@/services/agent';
import { toast } from '@/hooks/useToast';

interface AgentOpenAPIServicesTabProps {
  services: OpenAPIServiceConfig[];
  onChange: (services: OpenAPIServiceConfig[]) => void;
  readonly?: boolean;
}

interface ServiceEditorProps {
  service: OpenAPIServiceConfig;
  index: number;
  onUpdate: (index: number, service: OpenAPIServiceConfig) => void;
  onRemove: (index: number) => void;
  readonly?: boolean;
}

function ServiceEditor({ service, index, onUpdate, onRemove, readonly }: ServiceEditorProps) {
  const t = useTranslations('agent.openapi');
  const [parsing, setParsing] = useState(false);
  const [parsedSpec, setParsedSpec] = useState<ParseSpecResponse | null>(null);
  const [showAuth, setShowAuth] = useState(!!service.auth && service.auth.type !== 'none');
  const [expanded, setExpanded] = useState(false);

  const handleParseSpec = useCallback(async () => {
    if (!service.spec_url && !service.spec_content) {
      toast({ title: t('specRequired'), variant: 'destructive' });
      return;
    }
    setParsing(true);
    try {
      const result = await parseOpenAPISpec({
        spec_url: service.spec_url,
        spec_content: service.spec_content,
      });
      setParsedSpec(result);
      if (!service.name && result.title) {
        onUpdate(index, {
          ...service,
          name: result.title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .slice(0, 30),
          description: result.description || undefined,
        });
      }
      toast({ title: t('parseSuccess') });
    } catch (e) {
      toast({ title: t('parseFailed'), description: String(e), variant: 'destructive' });
    } finally {
      setParsing(false);
    }
  }, [service, index, onUpdate, t]);

  const updateField = <K extends keyof OpenAPIServiceConfig>(key: K, value: OpenAPIServiceConfig[K]) => {
    onUpdate(index, { ...service, [key]: value });
  };

  const updateAuth = (auth: OpenAPIAuthConfig | undefined) => {
    onUpdate(index, { ...service, auth });
  };

  return (
    <div className="rounded-lg border border-border/60 bg-background/50 p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-medium text-foreground hover:text-primary transition-colors"
        >
          <span
            className={cn(
              'inline-block w-2 h-2 rounded-full',
              service.enabled ? 'bg-emerald-500' : 'bg-muted-foreground/30',
            )}
          />
          <span>{service.name || t('unnamed')}</span>
          <span className="text-xs text-muted-foreground">{expanded ? '▲' : '▼'}</span>
        </button>
        <div className="flex items-center gap-2">
          <Switch
            checked={service.enabled}
            onCheckedChange={(checked) => updateField('enabled', checked)}
            disabled={readonly}
          />
          {!readonly && (
            <Button variant="ghost" size="sm" onClick={() => onRemove(index)} className="h-7 w-7 p-0 text-destructive">
              ×
            </Button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-border/40">
          {/* Spec URL or Content */}
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t('specUrl')}</label>
            <div className="flex gap-2 mt-1">
              <Input
                placeholder="https://api.example.com/openapi.json"
                value={service.spec_url || ''}
                onChange={(e) => {
                  updateField('spec_url', e.target.value || undefined);
                  if (e.target.value) updateField('spec_content', undefined);
                }}
                disabled={readonly || !!service.spec_content}
                className="flex-1"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleParseSpec}
                disabled={parsing || readonly}
                className="shrink-0"
              >
                {parsing ? '...' : t('parse')}
              </Button>
            </div>
            {!service.spec_url && (
              <textarea
                placeholder={t('specContentPlaceholder')}
                value={service.spec_content || ''}
                onChange={(e) => updateField('spec_content', e.target.value || undefined)}
                disabled={readonly}
                className="mt-2 w-full h-20 rounded-full border border-input bg-background px-3 py-2 text-xs resize-y font-mono"
                rows={3}
              />
            )}
          </div>

          {/* Name + Timeout */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('namespace')}</label>
              <Input
                placeholder="my_api"
                value={service.name || ''}
                onChange={(e) => updateField('name', e.target.value)}
                disabled={readonly}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('timeout')}</label>
              <Input
                type="number"
                min={1}
                max={300}
                placeholder="30"
                value={service.request_timeout ?? ''}
                onChange={(e) =>
                  updateField('request_timeout', e.target.value ? parseInt(e.target.value, 10) : undefined)
                }
                disabled={readonly}
                className="mt-1"
              />
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t('description')}</label>
            <Input
              placeholder={t('descriptionPlaceholder')}
              value={service.description || ''}
              onChange={(e) => updateField('description', e.target.value || undefined)}
              disabled={readonly}
              className="mt-1"
            />
          </div>

          {/* Endpoint Selection */}
          {parsedSpec && parsedSpec.endpoints.length > 0 && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('endpoints')}</label>
              <div className="mt-1 max-h-32 overflow-y-auto rounded-full border border-border/40 p-2 space-y-1">
                {parsedSpec.endpoints.map((ep) => {
                  const isSelected =
                    !service.selected_endpoints?.length || service.selected_endpoints.includes(ep.operation_id);
                  return (
                    <label key={ep.operation_id} className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => {
                          const isCurrentlyAll = !service.selected_endpoints || service.selected_endpoints.length === 0;
                          const allIds = parsedSpec.endpoints.map((x) => x.operation_id);

                          if (e.target.checked) {
                            if (isCurrentlyAll) return;
                            const next = Array.from(new Set([...service.selected_endpoints!, ep.operation_id]));
                            updateField('selected_endpoints', next.length === allIds.length ? undefined : next);
                          } else {
                            const currentList = isCurrentlyAll ? allIds : service.selected_endpoints!;
                            const next = currentList.filter((id) => id !== ep.operation_id);
                            if (next.length === 0) {
                              toast({ title: 'Error', description: '必须至少保留一个端点', variant: 'destructive' });
                              return;
                            }
                            updateField('selected_endpoints', next);
                          }
                        }}
                        disabled={readonly}
                        className="rounded"
                      />
                      <span className="uppercase font-mono text-[10px] w-10 text-muted-foreground">{ep.method}</span>
                      <span className="truncate">{ep.path}</span>
                      {ep.summary && <span className="text-muted-foreground truncate ml-auto">— {ep.summary}</span>}
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {/* Auth Section */}
          <div>
            <button
              type="button"
              onClick={() => setShowAuth(!showAuth)}
              className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              {t('authentication')} {showAuth ? '▲' : '▼'}
            </button>
            {showAuth && <AuthEditor auth={service.auth} onChange={updateAuth} readonly={readonly} />}
          </div>

          {/* Parsed Spec Preview */}
          {parsedSpec && (
            <div className="rounded-full border border-border/40 bg-muted/30 p-2 text-xs space-y-1">
              <div className="font-medium text-foreground">
                {parsedSpec.title} v{parsedSpec.version}
              </div>
              <div className="text-muted-foreground">{parsedSpec.description}</div>
              <div className="text-muted-foreground">
                {t('endpoints')}: {parsedSpec.endpoint_count} | {t('tags')}: {Object.keys(parsedSpec.tags).join(', ')}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AuthEditor({
  auth,
  onChange,
  readonly,
}: {
  auth?: OpenAPIAuthConfig;
  onChange: (auth: OpenAPIAuthConfig | undefined) => void;
  readonly?: boolean;
}) {
  const t = useTranslations('agent.openapi.auth');
  const currentType = auth?.type || 'none';

  const setType = (type: OpenAPIAuthType) => {
    if (type === 'none') {
      onChange(undefined);
    } else {
      onChange({ ...auth, type });
    }
  };

  return (
    <div className="mt-2 space-y-2 pl-2 border-l-2 border-border/30">
      <select
        value={currentType}
        onChange={(e) => setType(e.target.value as OpenAPIAuthType)}
        disabled={readonly}
        className="w-full h-8 rounded-full border border-input bg-background px-2 text-xs"
      >
        <option value="none">{t('none')}</option>
        <option value="api_key">{t('apiKey')}</option>
        <option value="bearer">{t('bearer')}</option>
        <option value="basic">{t('basic')}</option>
        <option value="oauth2_client_credentials">{t('oauth2')}</option>
      </select>

      {currentType === 'api_key' && (
        <div className="space-y-2">
          <Input
            placeholder={t('apiKeyHeader')}
            value={auth?.api_key_header || ''}
            onChange={(e) => onChange({ ...auth!, api_key_header: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
          <Input
            type="password"
            placeholder={t('apiKeyValue')}
            value={auth?.api_key || ''}
            onChange={(e) => onChange({ ...auth!, api_key: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
        </div>
      )}

      {currentType === 'bearer' && (
        <Input
          type="password"
          placeholder={t('bearerToken')}
          value={auth?.bearer_token || ''}
          onChange={(e) => onChange({ ...auth!, bearer_token: e.target.value })}
          disabled={readonly}
          className="text-xs h-8"
        />
      )}

      {currentType === 'basic' && (
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder={t('username')}
            value={auth?.username || ''}
            onChange={(e) => onChange({ ...auth!, username: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
          <Input
            type="password"
            placeholder={t('password')}
            value={auth?.password || ''}
            onChange={(e) => onChange({ ...auth!, password: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
        </div>
      )}

      {currentType === 'oauth2_client_credentials' && (
        <div className="space-y-2">
          <Input
            placeholder={t('tokenUrl')}
            value={auth?.token_url || ''}
            onChange={(e) => onChange({ ...auth!, token_url: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
          <div className="grid grid-cols-2 gap-2">
            <Input
              placeholder={t('clientId')}
              value={auth?.client_id || ''}
              onChange={(e) => onChange({ ...auth!, client_id: e.target.value })}
              disabled={readonly}
              className="text-xs h-8"
            />
            <Input
              type="password"
              placeholder={t('clientSecret')}
              value={auth?.client_secret || ''}
              onChange={(e) => onChange({ ...auth!, client_secret: e.target.value })}
              disabled={readonly}
              className="text-xs h-8"
            />
          </div>
          <Input
            placeholder={t('scopes')}
            value={(auth?.scopes || []).join(', ')}
            onChange={(e) =>
              onChange({
                ...auth!,
                scopes: e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            disabled={readonly}
            className="text-xs h-8"
          />
        </div>
      )}
    </div>
  );
}

export function AgentOpenAPIServicesTab({ services, onChange, readonly }: AgentOpenAPIServicesTabProps) {
  const t = useTranslations('agent.openapi');
  const [presets, setPresets] = useState<SaaSPreset[]>([]);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const [showPresets, setShowPresets] = useState(false);

  useEffect(() => {
    async function loadPresets() {
      setLoadingPresets(true);
      try {
        const data = await getSaaSPresets();
        setPresets(data);
      } catch (e) {
        console.error('Failed to load presets', e);
      } finally {
        setLoadingPresets(false);
      }
    }
    loadPresets();
  }, []);

  const handleAdd = () => {
    onChange([
      ...services,
      {
        name: '',
        enabled: true,
        request_timeout: 30,
        max_retries: 2,
      },
    ]);
  };

  const handleApplyPreset = (preset: SaaSPreset) => {
    onChange([
      ...services,
      {
        name: preset.name.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
        description: preset.description,
        spec_url: preset.spec_url,
        enabled: true,
        auth: preset.auth_type !== 'none' ? { type: preset.auth_type as OpenAPIAuthType } : undefined,
        selected_endpoints: preset.selected_endpoints,
        request_timeout: 30,
        max_retries: 2,
      },
    ]);
    setShowPresets(false);
    toast({ title: `Added ${preset.name} connector` });
  };

  const handleUpdate = (index: number, updated: OpenAPIServiceConfig) => {
    const next = [...services];
    next[index] = updated;
    onChange(next);
  };

  const handleRemove = (index: number) => {
    onChange(services.filter((_, i) => i !== index));
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">{t('title')}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('subtitle')}</p>
        </div>
        {!readonly && (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setShowPresets(!showPresets)} className="h-7 text-xs">
              {t('addFromPreset') || '技能超市'}
            </Button>
            <Button variant="outline" size="sm" onClick={handleAdd} className="h-7 text-xs">
              + {t('add')}
            </Button>
          </div>
        )}
      </div>

      {showPresets && (
        <div className="mb-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-3 bg-muted/30 rounded-lg border border-border/50">
          {loadingPresets ? (
            <div className="text-xs text-muted-foreground">Loading presets...</div>
          ) : presets.length === 0 ? (
            <div className="text-xs text-muted-foreground">No presets available.</div>
          ) : (
            presets.map((preset) => (
              <div
                key={preset.name}
                className="border border-border/50 rounded-full p-3 hover:border-primary/50 transition-colors bg-background flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    {preset.icon_url && <img src={preset.icon_url} alt="" className="w-4 h-4" />}
                    <h4 className="text-sm font-semibold">{preset.name}</h4>
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2">{preset.description}</p>
                </div>
                <Button
                  size="sm"
                  variant="default"
                  className="mt-3 w-full text-xs h-7"
                  onClick={() => handleApplyPreset(preset)}
                >
                  启用
                </Button>
              </div>
            ))
          )}
        </div>
      )}

      {services.length === 0 ? (
        <div className="text-center py-6 text-sm text-muted-foreground">{t('empty')}</div>
      ) : (
        <div className="space-y-2">
          {services.map((svc, i) => (
            <ServiceEditor
              key={i}
              service={svc}
              index={i}
              onUpdate={handleUpdate}
              onRemove={handleRemove}
              readonly={readonly}
            />
          ))}
        </div>
      )}
    </div>
  );
}

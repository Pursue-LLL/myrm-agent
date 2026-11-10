'use client';

/**
 * [INPUT] @/services/agent::OpenAPIServiceConfig, @/services/agentOpenApi::parseOpenAPISpec (POS: OpenAPI 服务配置与规格解析), ./OpenAPIAuthEditor, ./openApiTokenBudget
 * [OUTPUT] ServiceEditor: 单个 OpenAPI 服务的编辑卡片（名称、规格地址或内容的解析、端点勾选、鉴权、超时、启停与删除）
 * [POS] AgentOpenAPIServicesTab 列表里的服务条目，字段变化经 onUpdate / onRemove 回传。
 */

import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { type OpenAPIServiceConfig, type OpenAPIAuthConfig } from '@/services/agent';
import { type ParseSpecResponse, parseOpenAPISpec } from '@/services/agentOpenApi';
import { toast } from '@/hooks/shared/useToast';
import { OPENAPI_DIRECT_TOKEN_BUDGET, estimateEndpointTokenLoad } from './openApiTokenBudget';
import { AuthEditor } from './OpenAPIAuthEditor';

interface ServiceEditorProps {
  service: OpenAPIServiceConfig;
  index: number;
  onUpdate: (index: number, service: OpenAPIServiceConfig) => void;
  onRemove: (index: number) => void;
  readonly?: boolean;
}

export function ServiceEditor({ service, index, onUpdate, onRemove, readonly }: ServiceEditorProps) {
  const t = useTranslations('agent.openapi');
  const tCommon = useTranslations('common');
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

  const selectedEndpointCount =
    !service.selected_endpoints || service.selected_endpoints.length === 0
      ? (parsedSpec?.endpoint_count ?? 0)
      : service.selected_endpoints.length;
  const estimatedServiceTokens = estimateEndpointTokenLoad(selectedEndpointCount);
  const serviceOverBudget = parsedSpec !== null && estimatedServiceTokens > OPENAPI_DIRECT_TOKEN_BUDGET;

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
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onRemove(index)}
              className="h-7 w-7 p-0 text-destructive-text"
            >
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
                  if (e.target.value) {
                    updateField('spec_content', undefined);
                  }
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
                            if (isCurrentlyAll) {
                              return;
                            }
                            const next = Array.from(new Set([...(service.selected_endpoints ?? []), ep.operation_id]));
                            updateField('selected_endpoints', next.length === allIds.length ? undefined : next);
                          } else {
                            const currentList = isCurrentlyAll ? allIds : (service.selected_endpoints ?? []);
                            const next = currentList.filter((id) => id !== ep.operation_id);
                            if (next.length === 0) {
                              toast({
                                title: tCommon('errorTitle'),
                                description: t('atLeastOneEndpoint'),
                                variant: 'destructive',
                              });
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

          {serviceOverBudget && (
            <p className="text-xs text-amber-600 dark:text-amber-400">{t('turn1BudgetServiceWarning')}</p>
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

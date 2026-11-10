'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { type OpenAPIServiceConfig, type OpenAPIAuthType } from '@/services/agent';
import { getSaaSPresets, type SaaSPreset } from '@/services/agentOpenApi';
import { toast } from '@/hooks/shared/useToast';
import { OPENAPI_DIRECT_TOKEN_BUDGET, estimateEndpointTokenLoad } from './openApiTokenBudget';
import { ServiceEditor } from './OpenAPIServiceEditor';

function countExplicitSelectedEndpoints(services: OpenAPIServiceConfig[]): number {
  return services
    .filter((service) => service.enabled !== false)
    .reduce((total, service) => {
      const selected = service.selected_endpoints;
      if (!selected || selected.length === 0) {
        return total;
      }
      return total + selected.length;
    }, 0);
}

interface AgentOpenAPIServicesTabProps {
  services: OpenAPIServiceConfig[];
  onChange: (services: OpenAPIServiceConfig[]) => void;
  readonly?: boolean;
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
    toast({ title: t('presetAdded', { name: preset.name }) });
  };

  const handleUpdate = (index: number, updated: OpenAPIServiceConfig) => {
    const next = [...services];
    next[index] = updated;
    onChange(next);
  };

  const handleRemove = (index: number) => {
    onChange(services.filter((_, i) => i !== index));
  };

  const explicitEndpointCount = countExplicitSelectedEndpoints(services);
  const estimatedAggregateTokens = estimateEndpointTokenLoad(explicitEndpointCount);
  const aggregateOverBudget = explicitEndpointCount > 0 && estimatedAggregateTokens > OPENAPI_DIRECT_TOKEN_BUDGET;

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
              {t('addFromPreset')}
            </Button>
            <Button variant="outline" size="sm" onClick={handleAdd} className="h-7 text-xs">
              + {t('add')}
            </Button>
          </div>
        )}
      </div>

      {aggregateOverBudget && (
        <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">
          {t('turn1BudgetWarning', {
            tokens: estimatedAggregateTokens,
            budget: OPENAPI_DIRECT_TOKEN_BUDGET,
          })}
        </p>
      )}

      {showPresets && (
        <div className="mb-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-3 bg-muted/30 rounded-lg border border-border/50">
          {loadingPresets ? (
            <div className="text-xs text-muted-foreground">{t('presetsLoading')}</div>
          ) : presets.length === 0 ? (
            <div className="text-xs text-muted-foreground">{t('presetsEmpty')}</div>
          ) : (
            presets.map((preset) => (
              <div
                key={preset.name}
                className="border border-border/50 rounded-full p-3 hover:border-primary/50 transition-colors bg-background flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    {preset.icon_url && (
                      // oxlint-disable-next-line next/no-img-element -- connector icons come from arbitrary hosts, which next/image cannot optimize
                      <img src={preset.icon_url} alt="" className="w-4 h-4" />
                    )}
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
                  {t('presetEnable')}
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

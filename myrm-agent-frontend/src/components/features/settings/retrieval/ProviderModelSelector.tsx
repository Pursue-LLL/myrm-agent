'use client';

import { memo, useCallback, useId, useMemo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { IconLoader, IconCheckCircle, IconXCircle, IconExternalLink } from '@/components/features/icons/PremiumIcons';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Button } from '@/components/primitives/button';
import OptionSelect from '../OptionSelect';
import { getPresetModel, type ProviderConfig } from '@/lib/search/retrievalProviders';
import { localizeReactNode } from '@/lib/utils/locale';
import type { ApplyStatus, ProviderModelConfig } from '@/store/retrieval/types';
import ApiKeyField from './ApiKeyField';
import ApplyOutcome from './ApplyOutcome';

interface ProviderModelSelectorProps {
  value: ProviderModelConfig;
  onChange: (config: ProviderModelConfig) => void;
  providers: ProviderConfig[];
  applyStatus: ApplyStatus;
  applyMessage?: string;
  /** Whether a config has been validated and synced at least once. */
  isApplied: boolean;
  onApply: () => Promise<unknown>;
}

/**
 * Provider + model + API key selector for one retrieval model.
 *
 * Switching the provider selects that provider's preset model. Providers without a model list
 * (OpenAI Compatible) take a free-text model name and an API base URL.
 */
const ProviderModelSelector = memo<ProviderModelSelectorProps>(
  ({ value, onChange, providers, applyStatus, applyMessage, isApplied, onApply }) => {
    const t = useTranslations('settings.retrieval');
    const locale = useLocale();
    const modelListId = useId();

    const currentProvider = useMemo(() => providers.find((p) => p.id === value.provider), [providers, value.provider]);

    const providerOptions = useMemo(() => providers.map((p) => ({ value: p.id, label: p.name })), [providers]);

    const modelOptions = useMemo(
      () =>
        (currentProvider?.models ?? []).map((m) => ({
          value: m.value,
          label: m.label,
          description: m.description,
        })),
      [currentProvider],
    );

    const requiresApiBase = currentProvider?.requiresApiBase || false;

    // Providers without a model list (OpenAI Compatible) take any model name.
    const allowCustomModel = currentProvider?.models.length === 0;

    const handleProviderChange = useCallback(
      (providerId: string) => {
        const provider = providers.find((p) => p.id === providerId);
        onChange({
          ...value,
          provider: providerId,
          model: getPresetModel(providers, providerId),
          // The API base only carries over between providers that need one.
          apiBase: provider?.requiresApiBase ? value.apiBase : undefined,
        });
      },
      [providers, value, onChange],
    );

    const handleModelChange = useCallback(
      (model: string) => {
        onChange({ ...value, model });
      },
      [value, onChange],
    );

    const handleApiKeyChange = useCallback(
      (apiKey: string) => {
        onChange({ ...value, apiKey });
      },
      [value, onChange],
    );

    const handleApiBaseChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange({ ...value, apiBase: e.target.value });
      },
      [value, onChange],
    );

    const applied = isApplied && applyStatus === 'success';

    return localizeReactNode(
      <div className="space-y-4">
        <div className="space-y-3">
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('provider')}</Label>
            <OptionSelect
              value={value.provider}
              options={providerOptions}
              onChange={handleProviderChange}
              className="w-full"
            />
            {currentProvider?.modelListUrl && (
              <a
                href={currentProvider.modelListUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                <IconExternalLink className="w-3 h-3" />
                {t('viewProviderModels')}
              </a>
            )}
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('modelName')}</Label>
            {allowCustomModel ? (
              <Input
                value={value.model}
                onChange={(e) => handleModelChange(e.target.value)}
                placeholder={t('modelNamePlaceholder')}
                className="font-mono text-sm"
              />
            ) : (
              <>
                <Input
                  list={modelListId}
                  value={value.model}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder={t('modelNamePlaceholder')}
                  className="font-mono text-sm"
                />
                <datalist id={modelListId}>
                  {modelOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </datalist>
                {modelOptions.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {modelOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => handleModelChange(option.value)}
                        className={`px-3 py-2.5 text-left rounded-lg border transition-all ${
                          value.model === option.value
                            ? 'bg-primary text-primary-foreground border-primary'
                            : 'bg-card hover:bg-accent hover:border-accent-foreground/20 border-border'
                        }`}
                      >
                        <div className="flex flex-col gap-1">
                          <span className="font-mono text-xs font-medium leading-tight">{option.label}</span>
                          {option.description && (
                            <span
                              className={`text-[10px] leading-tight ${
                                value.model === option.value ? 'text-primary-foreground/80' : 'text-muted-foreground'
                              }`}
                            >
                              {option.description}
                            </span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <ApiKeyField value={value.apiKey} onChange={handleApiKeyChange} />

          {requiresApiBase && (
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t('apiBase')}</Label>
              <Input
                value={value.apiBase || ''}
                onChange={handleApiBaseChange}
                placeholder={t('apiBasePlaceholder')}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">{t('apiBaseHint')}</p>
            </div>
          )}

          <div className="space-y-2">
            <Button
              type="button"
              size="sm"
              variant={applied ? 'default' : 'outline'}
              onClick={() => void onApply()}
              disabled={applyStatus === 'applying'}
            >
              {applyStatus === 'applying' && <IconLoader className="mr-2 h-3 w-3 animate-spin" />}
              {applied && <IconCheckCircle className="mr-2 h-3 w-3" />}
              {applyStatus === 'error' && <IconXCircle className="mr-2 h-3 w-3" />}
              {applied ? t('apply.applied') : t('apply.button')}
            </Button>

            <ApplyOutcome status={applyStatus} message={applyMessage} />
          </div>
        </div>
      </div>,
      locale,
    );
  },
);

ProviderModelSelector.displayName = 'ProviderModelSelector';

export default ProviderModelSelector;

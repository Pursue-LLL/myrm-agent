'use client';

import { memo, useState, useEffect, useMemo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { IconX, IconCheck, IconLoader, IconAlertCircle, IconHelpCircle } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import {
  SearchServiceConfigItem,
  SearchServiceConfig,
  ValidationResult,
} from '@/store/config/types';
import { InputField } from './FormFields';
import Tooltip from './Tooltip';
import OptionSelect from './OptionSelect';
import { useDeployMode } from '@/hooks/shared/useDeployMode';
import useConfigStore from '@/store/useConfigStore';
import { fetchSearchProviders, isSoftSearchServiceValidationFailure, type SearchProviderManifestEntry } from '@/services/llm-config';
import { buildSearxngExtraParams, detectSearxngPreset, type SearxngRegionPreset } from '@/lib/search/searxngPresets';
import { suggestNextPriority } from '@/store/config/searchService';

interface SearchServiceEditDialogProps {
  isOpen: boolean;
  onClose: () => void;
  config: SearchServiceConfigItem | null;
  isCreating: boolean;
  onSave: (config: SearchServiceConfigItem) => void;
  onValidate: (config: SearchServiceConfig) => Promise<ValidationResult>;
}

const SearchServiceEditDialog = memo(
  ({ isOpen, onClose, config, isCreating, onSave, onValidate }: SearchServiceEditDialogProps) => {
    const t = useTranslations('settings');
    const locale = useLocale();
    const isZh = locale.startsWith('zh');
    const { isLocal } = useDeployMode();

    const [name, setName] = useState('');
    const [searchService, setSearchService] = useState('tavily');
    const [apiKey, setApiKey] = useState('');
    const [apiBase, setApiBase] = useState('');
    const [extraParams, setExtraParams] = useState('');
    const [regionPreset, setRegionPreset] = useState<SearxngRegionPreset>('global');
    const [enabled, setEnabled] = useState(false);
    const [priority, setPriority] = useState(1);
    const [providers, setProviders] = useState<SearchProviderManifestEntry[]>([]);
    const [maxChainSize, setMaxChainSize] = useState(5);
    const [providersLoading, setProvidersLoading] = useState(false);

    const [isValidating, setIsValidating] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [validationSuccess, setValidationSuccess] = useState(false);
    const [validationError, setValidationError] = useState('');
    const [validationLatency, setValidationLatency] = useState<number | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});

    const { searchServiceConfigs } = useConfigStore();

    const activeProvider = useMemo(
      () => providers.find((p) => p.slug === searchService),
      [providers, searchService],
    );

    const recommendedPriority = useMemo(() => {
      if (!isOpen || config) {
        return 1;
      }
      return suggestNextPriority(searchServiceConfigs);
    }, [isOpen, config, searchServiceConfigs]);

    const enabledByPriority = useMemo(() => {
      const enabled = searchServiceConfigs.filter((c) => c.enabled && c.id !== config?.id);
      return [...enabled].sort((a, b) => a.priority - b.priority);
    }, [searchServiceConfigs, config?.id]);

    const priorityOptions = useMemo(
      () =>
        Array.from({ length: maxChainSize }, (_, i) => {
          const value = i + 1;
          return { value: String(value), label: t('searchServicePriorityOption', { priority: value }) };
        }),
      [maxChainSize, t],
    );

    const searxngPresetOptions = useMemo(
      () => [
        { value: 'global', label: t('searchService.searxngPresetGlobal') },
        { value: 'china', label: t('searchService.searxngPresetChina') },
        { value: 'code', label: t('searchService.searxngPresetCode') },
        { value: 'academic', label: t('searchService.searxngPresetAcademic') },
      ],
      [t],
    );

    useEffect(() => {
      if (!isOpen) {
        return;
      }
      let cancelled = false;
      setProvidersLoading(true);
      void fetchSearchProviders(isLocal)
        .then((data) => {
          if (cancelled) return;
          setProviders(data.providers);
          setMaxChainSize(data.maxChainSize);
        })
        .catch(() => {
          if (cancelled) return;
          setProviders([]);
        })
        .finally(() => {
          if (!cancelled) setProvidersLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }, [isOpen, isLocal]);

    const resolveExtraParams = (): Record<string, unknown> | null => {
      if (searchService === 'searxng') {
        return buildSearxngExtraParams(regionPreset);
      }
      if (!extraParams.trim()) {
        return null;
      }
      try {
        return JSON.parse(extraParams) as Record<string, unknown>;
      } catch {
        return null;
      }
    };

    useEffect(() => {
      if (isOpen) {
        if (config) {
          setName(config.name || '');
          setSearchService(config.search_service);
          setApiKey(config.api_key || '');
          setApiBase(config.api_base || '');
          setExtraParams(config.extra_params ? JSON.stringify(config.extra_params, null, 2) : '');
          setRegionPreset(
            config.search_service === 'searxng'
              ? detectSearxngPreset(config.extra_params as Record<string, unknown> | null)
              : 'global',
          );
          setEnabled(config.enabled);
          setPriority(config.priority || 1);
        } else {
          setName('');
          setSearchService(isLocal ? 'searxng' : 'tavily');
          setApiKey('');
          setApiBase(isLocal ? 'http://127.0.0.1:8081' : '');
          setExtraParams('');
          setRegionPreset('global');
          setEnabled(false);
          setPriority(recommendedPriority);
        }
        setErrors({});
        setValidationError('');
        setValidationSuccess(false);
        setValidationLatency(null);
      }
    }, [isOpen, config, recommendedPriority, isLocal]);

    const validateForm = (): boolean => {
      const newErrors: Record<string, string> = {};

      const trimmedName = name.trim();
      if (trimmedName) {
        const isDuplicate = searchServiceConfigs.some(
          (c) => c.id !== config?.id && c.name?.trim().toLowerCase() === trimmedName.toLowerCase(),
        );
        if (isDuplicate) {
          newErrors.name = t('searchService.configNameDuplicate');
        }
      }

      if (!searchService) {
        newErrors.searchService = t('modelRequired');
      }

      const requiresKey = activeProvider?.requiresApiKey ?? searchService !== 'searxng';
      if (requiresKey && !apiKey) {
        newErrors.apiKey = t('apiKeyRequired');
      }

      const requiresBase = activeProvider?.requiresApiBase ?? searchService === 'searxng';
      if (requiresBase && !apiBase.trim()) {
        newErrors.apiBase = t('apiBaseRequired');
      }

      if (searchService !== 'searxng' && extraParams.trim()) {
        try {
          JSON.parse(extraParams);
        } catch {
          newErrors.extraParams = t('jsonFormatError');
        }
      }

      setErrors(newErrors);
      return Object.keys(newErrors).length === 0;
    };

    const handleValidate = async () => {
      if (!validateForm()) return;

      setIsValidating(true);
      setValidationError('');
      setValidationSuccess(false);

      try {
        const parsedExtraParams = resolveExtraParams();
        if (searchService !== 'searxng' && extraParams.trim() && parsedExtraParams === null) {
          setValidationError(t('jsonFormatError'));
          return;
        }

        const result = await onValidate({
          search_service: searchService,
          api_key: apiKey || null,
          api_base: apiBase || null,
          extra_params: parsedExtraParams,
        });

        if (result.success) {
          setValidationSuccess(true);
          setValidationLatency(result.latency || null);
        } else {
          setValidationError(result.message || t('searchServiceValidationFailed'));
          setValidationLatency(result.latency || null);
        }
      } catch (error) {
        setValidationError(error instanceof Error ? error.message : String(error));
      } finally {
        setIsValidating(false);
      }
    };

    const handleSave = async () => {
      if (!validateForm()) return;

      if (config?.enabled) {
        const existingConfigs = searchServiceConfigs.filter((c) => c.id !== config?.id);
        const hasConflict = existingConfigs.some((c) => c.priority === priority && c.enabled);

        if (hasConflict) {
          setErrors({ priority: t('duplicatePriorityError') });
          return;
        }
      }

      let parsedExtraParams: Record<string, unknown> | null = null;
      if (searchService === 'searxng') {
        parsedExtraParams = buildSearxngExtraParams(regionPreset);
      } else if (extraParams.trim()) {
        try {
          parsedExtraParams = JSON.parse(extraParams) as Record<string, unknown>;
        } catch {
          return;
        }
      }

      setIsSaving(true);
      setValidationError('');

      try {
        const result = await onValidate({
          search_service: searchService,
          api_key: apiKey || null,
          api_base: apiBase || null,
          extra_params: parsedExtraParams,
        });

        if (!result.success) {
          const warningMessage = result.message || t('searchServiceValidationFailed');
          setValidationError(warningMessage);
          setValidationSuccess(false);
          if (searchService !== 'searxng' && !isSoftSearchServiceValidationFailure(result)) {
            return;
          }
        }

        if (result.success) {
          setValidationSuccess(true);
        }
        setValidationLatency(result.latency ?? null);

        const newConfig: SearchServiceConfigItem = {
          id: config?.id || '',
          name: name.trim() || null,
          enabled,
          priority,
          search_service: searchService,
          api_key: apiKey || null,
          api_base: apiBase || null,
          extra_params: parsedExtraParams,
          latency: result.latency ?? validationLatency,
          createdAt: config?.createdAt || Date.now(),
        };

        onSave(newConfig);
      } catch (error) {
        setValidationError(error instanceof Error ? error.message : String(error));
        setValidationSuccess(false);
      } finally {
        setIsSaving(false);
      }
    };

    const handleServiceChange = (value: string) => {
      const entry = providers.find((p) => p.slug === value);
      if (entry && !entry.backendReady) {
        return;
      }
      setSearchService(value);
      setApiKey('');
      setApiBase(value === 'searxng' ? 'http://127.0.0.1:8081' : '');
      setExtraParams('');
      setRegionPreset('global');
      setErrors({});
      setValidationError('');
      setValidationSuccess(false);
    };

    const serviceOptions = useMemo(() => {
      if (providers.length > 0) {
        return providers.map((entry) => ({
          value: entry.slug,
          label: isZh ? entry.nameZh : entry.name,
          disabled: !entry.backendReady,
          description: !entry.backendReady ? t('searchServiceProviderNotReady') : undefined,
        }));
      }
      const fallback = [
        ...(isLocal ? [{ value: 'searxng', label: t('searxngFreeLocal') }] : []),
        { value: 'perplexity', label: 'Perplexity' },
        { value: 'tavily', label: 'Tavily' },
        { value: 'exa_ai', label: 'Exa AI' },
        { value: 'parallel_ai', label: 'Parallel AI' },
        { value: 'google_pse', label: 'Google PSE' },
        { value: 'dataforseo', label: 'DataForSEO' },
        { value: 'firecrawl', label: 'Firecrawl' },
        { value: 'brave', label: 'Brave Search' },
        { value: 'serper', label: 'Serper' },
      ];
      return fallback;
    }, [providers, isLocal, isZh, t]);

    const showApiKeyField = activeProvider?.requiresApiKey ?? searchService !== 'searxng';
    const showApiBaseField = activeProvider?.requiresApiBase ?? searchService === 'searxng';
    const isFormValid =
      searchService &&
      (!showApiKeyField || apiKey) &&
      (!showApiBaseField || !!apiBase.trim()) &&
      (!activeProvider || activeProvider.backendReady);

    if (!isOpen) return null;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />

        <div className="relative bg-background rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between px-6 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-foreground">
              {isCreating ? t('searchService.addConfig') : t('searchService.editConfig')}
            </h2>
            <button
              onClick={onClose}
              className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-secondary transition-colors"
            >
              <IconX className="w-5 h-5" />
            </button>
          </div>

          <div className="px-6 py-4 space-y-4">
            <InputField
              label={t('searchService.configName')}
              placeholder={t('searchService.configNamePlaceholder')}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setErrors((prev) => ({ ...prev, name: undefined }));
              }}
              error={errors.name}
            />

            <div className="flex flex-col space-y-1">
              <div className="flex items-center space-x-1">
                <p className="text-black/70 dark:text-white/70 text-sm">
                  {t('searchServiceType')} <span className="text-red-500">*</span>
                </p>
                <Tooltip content={t('searchServiceTypeTooltip')}>
                  <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
                </Tooltip>
              </div>
              {providersLoading ? (
                <p className="text-sm text-muted-foreground">{t('searchServiceLoadingProviders')}</p>
              ) : (
                <OptionSelect
                  value={searchService}
                  onChange={handleServiceChange}
                  error={errors.searchService}
                  hideDescription={false}
                  options={serviceOptions}
                />
              )}
            </div>

            {showApiKeyField && (
              <InputField
                label={t('searchApiKey')}
                placeholder={t('apiKeyPlaceholder')}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
                isPassword
                error={errors.apiKey}
              />
            )}

            {searchService === 'searxng' && !isLocal && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                <IconAlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                <p className="text-sm text-amber-800 dark:text-amber-300">{t('searxngSandboxWarning')}</p>
              </div>
            )}

            {showApiBaseField && (
              <InputField
                label={t('apiBase')}
                placeholder="http://127.0.0.1:8081"
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
                tooltip={t('apiBaseTooltip')}
                error={errors.apiBase}
              />
            )}

            {searchService === 'searxng' && (
              <div className="flex flex-col space-y-1">
                <div className="flex items-center space-x-1">
                  <p className="text-black/70 dark:text-white/70 text-sm">{t('searchService.searxngRegionPreset')}</p>
                  <Tooltip content={t('searchService.searxngRegionPresetTooltip')}>
                    <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
                  </Tooltip>
                </div>
                <OptionSelect
                  value={regionPreset}
                  onChange={(value) => setRegionPreset(value as SearxngRegionPreset)}
                  hideDescription
                  options={searxngPresetOptions}
                />
              </div>
            )}

            {searchService !== 'searxng' && (
              <div className="flex flex-col space-y-1">
                <div className="flex items-center space-x-1">
                  <p className="text-black/70 dark:text-white/70 text-sm">{t('extraParams')}</p>
                  <Tooltip content={t('extraParamsTooltip')}>
                    <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
                  </Tooltip>
                </div>
                <textarea
                  value={extraParams}
                  onChange={(e) => setExtraParams(e.target.value)}
                  placeholder={t('extraParamsPlaceholder')}
                  className={cn(
                    'bg-secondary w-full px-3 py-2 border border-border dark:text-white rounded-lg text-sm min-h-[80px] resize-y font-mono',
                    errors.extraParams && 'border-red-500',
                  )}
                />
                {errors.extraParams && <p className="text-xs text-red-500 font-medium">{errors.extraParams}</p>}
              </div>
            )}

            <div className="border-t border-border pt-4 mt-4">
              <div className="flex flex-col space-y-2">
                <div className="flex items-center space-x-1">
                  <p className="text-black/70 dark:text-white/70 text-sm font-medium">
                    {t('searchServicePriority')} <span className="text-red-500">*</span>
                  </p>
                  <Tooltip content={t('searchServicePriorityTooltip')}>
                    <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
                  </Tooltip>
                </div>
                <OptionSelect
                  value={String(priority)}
                  onChange={(value) => {
                    setPriority(Number(value));
                    setErrors((prev) => ({ ...prev, priority: undefined }));
                  }}
                  hideDescription
                  options={priorityOptions}
                  error={errors.priority}
                />

                {enabledByPriority.length > 0 && (
                  <div className="mt-2 p-2 bg-accent dark:bg-accent border border-border dark:border-border rounded-lg">
                    <p className="text-xs text-accent-foreground dark:text-accent-foreground font-medium mb-1">
                      {t('currentEnabledConfigs')}
                    </p>
                    <div className="space-y-0.5">
                      {enabledByPriority.map((item) => (
                        <p key={item.id} className="text-xs text-muted-foreground dark:text-muted-foreground">
                          • {t('searchServicePriorityOption', { priority: item.priority })}:{' '}
                          {item.name || item.search_service}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

                {errors.priority && <p className="text-xs text-red-500 font-medium">{errors.priority}</p>}
              </div>
            </div>

            {validationError && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800 flex items-start space-x-2">
                <IconAlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-400 font-medium">{validationError}</p>
              </div>
            )}

            {validationSuccess && (
              <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800 flex items-start space-x-2">
                <IconCheck className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                <p className="text-sm text-green-700 dark:text-green-400 font-medium">
                  {t('validationSuccess')}
                  {validationLatency && ` (${validationLatency}ms)`}
                </p>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-secondary/30">
            <button
              onClick={handleValidate}
              disabled={isValidating || !isFormValid}
              className={cn(
                'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors',
                isValidating || !isFormValid
                  ? 'bg-secondary text-muted-foreground cursor-not-allowed'
                  : 'bg-secondary text-foreground hover:bg-secondary/80',
              )}
            >
              {isValidating && <IconLoader className="w-3.5 h-3.5 animate-spin" />}
              {t('searchService.validate')}
            </button>

            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground rounded-lg transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleSave}
                disabled={!isFormValid || isSaving}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors',
                  !isFormValid || isSaving
                    ? 'bg-muted text-muted-foreground cursor-not-allowed'
                    : 'bg-primary hover:bg-primary/90 text-white',
                )}
              >
                {isSaving && <IconLoader className="w-3.5 h-3.5 animate-spin" />}
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  },
);

SearchServiceEditDialog.displayName = 'SearchServiceEditDialog';

export default SearchServiceEditDialog;

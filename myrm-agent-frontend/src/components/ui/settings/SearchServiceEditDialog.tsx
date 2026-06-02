'use client';

import { memo, useState, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { IconX, IconCheck, IconLoader, IconAlertCircle, IconHelpCircle } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import {
  SearchServiceConfigItem,
  SearchServiceConfig,
  SearchServiceType,
  ValidationResult,
} from '@/store/config/types';
import { InputField } from './FormFields';
import Tooltip from './Tooltip';
import OptionSelect from './OptionSelect';
import { useDeployMode } from '@/hooks/useDeployMode';
import useConfigStore from '@/store/useConfigStore';
import { isSoftSearchServiceValidationFailure } from '@/services/llm-config';
import { buildSearxngExtraParams, detectSearxngPreset, type SearxngRegionPreset } from '@/lib/search/searxngPresets';

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
    const { isLocal } = useDeployMode();

    // 表单状态
    const [name, setName] = useState('');
    const [searchService, setSearchService] = useState<SearchServiceType>('tavily');
    const [apiKey, setApiKey] = useState('');
    const [apiBase, setApiBase] = useState('');
    const [extraParams, setExtraParams] = useState('');
    const [regionPreset, setRegionPreset] = useState<SearxngRegionPreset>('global');
    const [enabled, setEnabled] = useState(false);
    const [role, setRole] = useState<'primary' | 'fallback'>('primary');

    // 验证状态
    const [isValidating, setIsValidating] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [validationSuccess, setValidationSuccess] = useState(false);
    const [validationError, setValidationError] = useState('');
    const [validationLatency, setValidationLatency] = useState<number | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});

    // 需要 API Key 的服务列表
    const servicesRequiringApiKey: SearchServiceType[] = [
      'perplexity',
      'tavily',
      'exa_ai',
      'parallel_ai',
      'google_pse',
      'dataforseo',
      'firecrawl',
    ];

    // 获取当前所有配置（用于智能角色推荐）
    const { searchServiceConfigs } = useConfigStore();

    // 智能推荐角色（仅在创建新配置时）
    const recommendedRole = useMemo(() => {
      if (!isOpen || config) {
        return 'primary';
      }

      const enabledConfigs = searchServiceConfigs.filter((c) => c.enabled);
      const hasPrimary = enabledConfigs.some((c) => c.role === 'primary');
      const hasFallback = enabledConfigs.some((c) => c.role === 'fallback');

      return hasPrimary && !hasFallback ? 'fallback' : 'primary';
    }, [isOpen, config, searchServiceConfigs]);

    // 计算当前已启用的配置信息（用于显示提示）
    const enabledConfigsInfo = useMemo(() => {
      const enabled = searchServiceConfigs.filter((c) => c.enabled && c.id !== config?.id);
      const primary = enabled.find((c) => c.role === 'primary');
      const fallback = enabled.find((c) => c.role === 'fallback');
      return { primary, fallback };
    }, [searchServiceConfigs, config?.id]);

    const searxngPresetOptions = useMemo(
      () => [
        { value: 'global', label: t('searchService.searxngPresetGlobal') },
        { value: 'china', label: t('searchService.searxngPresetChina') },
        { value: 'code', label: t('searchService.searxngPresetCode') },
        { value: 'academic', label: t('searchService.searxngPresetAcademic') },
      ],
      [t],
    );

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

    // 初始化表单
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
          setRole(config.role || 'primary');
        } else {
          // 创建新配置时重置表单
          setName('');
          setSearchService(isLocal ? 'searxng' : 'tavily');
          setApiKey('');
          setApiBase(isLocal ? 'http://127.0.0.1:8081' : '');
          setExtraParams('');
          setRegionPreset('global');
          setEnabled(false);
          setRole(recommendedRole);
        }
        setErrors({});
        setValidationError('');
        setValidationSuccess(false);
        setValidationLatency(null);
      }
    }, [isOpen, config, recommendedRole, isLocal]);

    // 表单验证
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

      if (servicesRequiringApiKey.includes(searchService) && !apiKey) {
        newErrors.apiKey = t('apiKeyRequired');
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

    // 验证配置
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

    // 保存配置（点击保存时自动验证，验证通过才可保存成功）
    const handleSave = async () => {
      if (!validateForm()) return;

      // 只有当配置已启用时才检查角色冲突
      // 未启用的配置可以自由设置任何角色，冲突将在启用时检查
      if (config?.enabled) {
        const existingConfigs = searchServiceConfigs.filter((c) => c.id !== config?.id);
        const hasConflict = existingConfigs.some((c) => c.role === role && c.enabled);

        if (hasConflict) {
          const conflictMessage = role === 'primary' ? t('onlyOnePrimaryService') : t('onlyOneFallbackService');
          setErrors({ role: conflictMessage });
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
          // 外部搜索服务可能因为配额/限流/瞬时网络问题无法通过验证，但配置本身仍可保存。
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
          enabled: enabled,
          role: role,
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

    // 处理服务类型变更
    const handleServiceChange = (value: string) => {
      const newService = value as SearchServiceType;
      setSearchService(newService);

      // 清除相关字段
      setApiKey('');
      setApiBase(newService === 'searxng' ? 'http://127.0.0.1:8081' : '');
      setExtraParams('');
      setRegionPreset('global');
      setErrors({});
      setValidationError('');
      setValidationSuccess(false);
    };

    const showApiKeyField = servicesRequiringApiKey.includes(searchService);
    const isFormValid =
      searchService && (!showApiKeyField || apiKey) && (searchService !== 'searxng' || !!apiBase.trim());

    // 根据部署模式动态生成选项列表
    const serviceOptions = [
      ...(isLocal ? [{ value: 'searxng', label: t('searxngFreeLocal') }] : []),
      { value: 'perplexity', label: 'Perplexity' },
      { value: 'tavily', label: 'Tavily' },
      { value: 'exa_ai', label: 'Exa AI' },
      { value: 'parallel_ai', label: 'Parallel AI' },
      { value: 'google_pse', label: 'Google PSE' },
      { value: 'dataforseo', label: 'DataForSEO' },
      { value: 'firecrawl', label: 'Firecrawl' },
    ];

    if (!isOpen) return null;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        {/* 背景遮罩 */}
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />

        {/* 对话框 */}
        <div className="relative bg-background rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          {/* 头部 */}
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

          {/* 内容 */}
          <div className="px-6 py-4 space-y-4">
            {/* 可选的配置名称 */}
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

            {/* 搜索服务类型 */}
            <div className="flex flex-col space-y-1">
              <div className="flex items-center space-x-1">
                <p className="text-black/70 dark:text-white/70 text-sm">
                  {t('searchServiceType')} <span className="text-red-500">*</span>
                </p>
                <Tooltip content={t('searchServiceTypeTooltip')}>
                  <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
                </Tooltip>
              </div>
              <OptionSelect
                value={searchService}
                onChange={handleServiceChange}
                error={errors.searchService}
                hideDescription
                options={serviceOptions}
              />
            </div>

            {/* API Key */}
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

            {/* SearXNG Sandbox 模式警告 */}
            {searchService === 'searxng' && !isLocal && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                <IconAlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                <p className="text-sm text-amber-800 dark:text-amber-300">{t('searxngSandboxWarning')}</p>
              </div>
            )}

            {/* API Base URL - 对 searxng 显示（可选配置本地实例地址） */}
            {searchService === 'searxng' && (
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

            {/* Extra Params - non-SearXNG services */}
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

            {/* 角色选择 */}
            <div className="border-t border-border pt-4 mt-4">
              <div className="flex flex-col space-y-2">
                <div className="flex items-center space-x-1">
                  <p className="text-black/70 dark:text-white/70 text-sm font-medium">
                    {t('searchServiceRole')} <span className="text-red-500">*</span>
                  </p>
                  <Tooltip content={t('searchServiceRoleTooltip')}>
                    <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
                  </Tooltip>
                </div>
                <div className="flex space-x-4">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={role === 'primary'}
                      onChange={() => {
                        setRole('primary');
                        setErrors((prev) => ({ ...prev, role: undefined }));
                      }}
                      className="w-4 h-4 accent-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm text-black dark:text-white">{t('primaryService')}</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={role === 'fallback'}
                      onChange={() => {
                        setRole('fallback');
                        setErrors((prev) => ({ ...prev, role: undefined }));
                      }}
                      className="w-4 h-4 accent-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm text-black dark:text-white">{t('fallbackService')}</span>
                  </label>
                </div>

                {/* 已启用配置信息提示 */}
                {(enabledConfigsInfo.primary || enabledConfigsInfo.fallback) && (
                  <div className="mt-2 p-2 bg-accent dark:bg-accent border border-border dark:border-border rounded-lg">
                    <p className="text-xs text-accent-foreground dark:text-accent-foreground font-medium mb-1">
                      {t('currentEnabledConfigs')}
                    </p>
                    <div className="space-y-0.5">
                      {enabledConfigsInfo.primary && (
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          • {t('primaryService')}:{' '}
                          {enabledConfigsInfo.primary.name || enabledConfigsInfo.primary.search_service}
                        </p>
                      )}
                      {enabledConfigsInfo.fallback && (
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          • {t('fallbackService')}:{' '}
                          {enabledConfigsInfo.fallback.name || enabledConfigsInfo.fallback.search_service}
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {errors.role && <p className="text-xs text-red-500 font-medium">{errors.role}</p>}
              </div>
            </div>

            {/* 验证错误 */}
            {validationError && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800 flex items-start space-x-2">
                <IconAlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-400 font-medium">{validationError}</p>
              </div>
            )}

            {/* 验证成功 */}
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

          {/* 底部操作 */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-secondary/30">
            {/* 验证按钮 */}
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

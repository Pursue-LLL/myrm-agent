'use client';

import { memo, useMemo, useCallback, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  IconLoader,
  IconCheckCircle,
  IconXCircle,
  IconExternalLink,
  IconEye,
  IconEyeOff,
} from '@/components/features/icons/PremiumIcons';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Button } from '@/components/primitives/button';
import OptionSelect from '../OptionSelect';
import { ProviderConfig, toLiteLLMFormat } from '@/lib/search/retrievalProviders';
import { localizeReactNode } from '@/lib/utils/localeText';

export interface ProviderModelConfig {
  provider: string;
  model: string;
  apiKey: string;
  apiBase?: string;
  validated?: boolean; // 是否已验证
}

type ValidationState = 'idle' | 'loading' | 'success' | 'error';

interface ValidationResult {
  state: ValidationState;
  message?: string;
}

interface ProviderModelSelectorProps {
  value: ProviderModelConfig;
  onChange: (config: ProviderModelConfig) => void;
  providers: ProviderConfig[];
  serviceType: 'embedding' | 'reranker'; // 服务类型
  label?: string;
  disabled?: boolean;
  // 外部应用状态（由父组件管理）
  applyStatus?: 'idle' | 'applying' | 'success' | 'error';
  applyMessage?: string;
  isApplied?: boolean; // 是否已应用
  onApply?: () => Promise<{ success: boolean; message: string }>; // 应用函数
}

/**
 * Provider + Model + API 配置选择器
 *
 * 支持：
 * 1. 选择提供商（Provider）
 * 2. 选择或输入模型名称
 * 3. 输入 API Key
 * 4. 输入 API Base（OpenAI Compatible）
 * 5. 验证配置有效性
 */
const EMPTY_CONFIG: ProviderModelConfig = { provider: '', model: '', apiKey: '' };

const ProviderModelSelector = memo<ProviderModelSelectorProps>(
  ({
    value = EMPTY_CONFIG,
    onChange,
    providers,
    serviceType,
    label,
    disabled = false,
    applyStatus,
    applyMessage,
    isApplied = false,
    onApply,
  }) => {
    const t = useTranslations('settings.retrieval');
    const locale = useLocale();

    // 密码显示/隐藏状态
    const [showPassword, setShowPassword] = useState(false);

    // 翻译应用消息
    const translateApplyMessage = useCallback(
      (message: string | undefined): string | undefined => {
        if (!message) return undefined;

        // 常见错误消息的精确匹配
        if (message === 'Missing required fields') {
          return t('validationMessages.missingRequiredFields');
        }
        if (message === 'Network error') {
          return t('validationMessages.networkError');
        }
        if (message === 'Validation failed') {
          return t('validationMessages.validationFailed');
        }

        // 解析维度信息：Validation successful (dimension: 1024)
        const dimensionMatch = message.match(/Validation successful \(dimension: (\d+)\)/);
        if (dimensionMatch) {
          return t('validationMessages.successWithDimension', { dimension: dimensionMatch[1] });
        }

        // 解析结果数：Validation successful (returned 1 result / 2 results)
        const resultsMatch = message.match(/Validation successful \(returned (\d+) results?\)/);
        if (resultsMatch) {
          const count = parseInt(resultsMatch[1]);
          return t('validationMessages.successWithResults', {
            count: count.toString(),
            plural: count > 1 ? 's' : '',
          });
        }

        // 解析失败消息：Validation failed: Error
        const failedMatch = message.match(/Validation failed: (.+)/);
        if (failedMatch) {
          return t('validationMessages.failedWithError', { error: failedMatch[1] });
        }

        // 如果无法匹配，返回原消息
        return message;
      },
      [t],
    );

    // 使用外部应用状态
    const effectiveStatus = applyStatus || 'idle';
    const effectiveMessage = translateApplyMessage(applyMessage);

    // 内部应用状态（仅在没有外部状态时使用，保留向后兼容）
    const [validation, setValidation] = useState<ValidationResult>({
      state: 'idle',
    });

    // 当前选中的 Provider 配置
    const currentProvider = useMemo(() => {
      return providers.find((p) => p.id === value?.provider);
    }, [providers, value?.provider]);

    // Provider 选项
    const providerOptions = useMemo(() => {
      return providers.map((p) => ({
        value: p.id,
        label: p.name,
      }));
    }, [providers]);

    // Model 选项
    const modelOptions = useMemo(() => {
      if (!currentProvider || currentProvider.models.length === 0) {
        return [];
      }
      return currentProvider.models.map((m) => ({
        value: m.value,
        label: m.label,
        description: m.description,
      }));
    }, [currentProvider]);

    // 是否需要显示 API Base
    const requiresApiBase = currentProvider?.requiresApiBase || false;

    // 是否可以自由输入模型名（没有预定义模型列表）
    const allowCustomModel = currentProvider?.models.length === 0;

    // 处理 Provider 变更（直接调用，不需要包装）
    const handleProviderChange = useCallback(
      (providerId: string) => {
        const provider = providers.find((p) => p.id === providerId);
        const defaultModel = provider?.models[0]?.value || '';

        onChange({
          ...value,
          provider: providerId,
          model: defaultModel,
          // 切换 provider 时清空 API Base（除非新 provider 也需要）
          apiBase: provider?.requiresApiBase ? value.apiBase : undefined,
        });
      },
      [providers, value, onChange],
    );

    // 处理 Model 变更
    const handleModelChange = useCallback(
      (model: string) => {
        onChange({ ...value, model });
      },
      [value, onChange],
    );

    // 处理 API Key 变更
    const handleApiKeyChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange({ ...value, apiKey: e.target.value });
      },
      [value, onChange],
    );

    // 处理 API Base 变更
    const handleApiBaseChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange({ ...value, apiBase: e.target.value });
      },
      [value, onChange],
    );

    // 内部应用函数（仅在没有外部应用函数时使用）
    const handleApply = useCallback(async () => {
      // 如果有外部应用函数，优先使用
      if (onApply) {
        return onApply();
      }

      // 否则使用内部验证逻辑（保留向后兼容）
      console.warn('[ProviderModelSelector] Using internal apply. Consider using external apply via onApply prop.');

      // 检查必填字段
      if (!value.provider || !value.model || !value.apiKey) {
        setValidation({
          state: 'error',
          message: t('validation.missingFields'),
        });
        return;
      }

      if (requiresApiBase && !value.apiBase) {
        setValidation({
          state: 'error',
          message: t('validation.missingApiBase'),
        });
        return;
      }

      setValidation({ state: 'loading' });

      try {
        // 转换为 LiteLLM 格式
        const litellmModel = toLiteLLMFormat(value.provider, value.model);

        // 调用验证 API
        const endpoint =
          serviceType === 'embedding' ? '/api/retrieval/validate/embedding' : '/api/retrieval/validate/reranker';

        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: litellmModel,
            api_key: value.apiKey,
            api_base: value.apiBase || null,
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();

        if (result.success) {
          setValidation({
            state: 'success',
            message: result.message || t('validation.success'),
          });
        } else {
          setValidation({
            state: 'error',
            message: result.error || result.message || t('validation.failed'),
          });
        }
      } catch (error) {
        setValidation({
          state: 'error',
          message: error instanceof Error ? error.message : t('validation.networkError'),
        });
      }
    }, [value, onApply, requiresApiBase, serviceType, t]);

    return localizeReactNode(
      <div className="space-y-4">
        {label && <Label className="text-base font-medium">{label}</Label>}

        <div className="space-y-3">
          {/* Provider 选择 */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('provider')}</Label>
            <OptionSelect
              value={value.provider}
              options={providerOptions}
              onChange={handleProviderChange}
              disabled={disabled}
              className="w-full"
            />
            {/* 显示提供商模型列表链接 */}
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

          {/* Model 选择/输入 */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('modelName')}</Label>
            {allowCustomModel ? (
              // OpenAI Compatible 等没有预设模型的 Provider，只能输入
              <Input
                value={value.model}
                onChange={(e) => handleModelChange(e.target.value)}
                placeholder={t('modelNamePlaceholder')}
                disabled={disabled}
                className="font-mono text-sm"
              />
            ) : (
              // 有预设模型的 Provider，支持选择或自定义输入
              <>
                <Input
                  list={`model-options-${value.provider}`}
                  value={value.model}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder={t('modelNamePlaceholder')}
                  disabled={disabled}
                  className="font-mono text-sm"
                />
                <datalist id={`model-options-${value.provider}`}>
                  {modelOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </datalist>
                {/* 显示常用模型快捷选择 */}
                {modelOptions.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {modelOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => handleModelChange(option.value)}
                        disabled={disabled}
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

          {/* API Key */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('apiKey')}</Label>
            <div className="relative">
              <Input
                type={showPassword ? 'text' : 'password'}
                value={value.apiKey}
                onChange={handleApiKeyChange}
                placeholder={t('apiKeyPlaceholder')}
                disabled={disabled}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowPassword(!showPassword)}
                disabled={disabled}
              >
                {showPassword ? (
                  <IconEyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <IconEye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">{t('apiKeyHint')}</p>
          </div>

          {/* API Base（仅 OpenAI Compatible 显示） */}
          {requiresApiBase && (
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t('apiBase')}</Label>
              <Input
                value={value.apiBase || ''}
                onChange={handleApiBaseChange}
                placeholder={t('apiBasePlaceholder')}
                disabled={disabled}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">{t('apiBaseHint')}</p>
            </div>
          )}

          {/* 应用按钮和状态 */}
          <div className="space-y-2">
            <Button
              type="button"
              size="sm"
              variant={isApplied && effectiveStatus === 'success' ? 'default' : 'outline'}
              onClick={onApply || handleApply}
              disabled={disabled || effectiveStatus === 'applying'}
            >
              {effectiveStatus === 'applying' && <IconLoader className="mr-2 h-3 w-3 animate-spin" />}
              {isApplied && effectiveStatus === 'success' && <IconCheckCircle className="mr-2 h-3 w-3" />}
              {effectiveStatus === 'error' && <IconXCircle className="mr-2 h-3 w-3" />}
              {isApplied && effectiveStatus === 'success' ? t('apply.applied') : t('apply.button')}
            </Button>

            {/* 应用结果消息 */}
            {(effectiveMessage || validation.message) && effectiveStatus !== 'idle' && (
              <p
                className={`text-xs ${
                  effectiveStatus === 'success'
                    ? 'text-green-600 dark:text-green-400'
                    : effectiveStatus === 'error'
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-muted-foreground'
                }`}
              >
                {effectiveMessage || validation.message}
              </p>
            )}
          </div>
        </div>
      </div>,
      locale,
    );
  },
);

ProviderModelSelector.displayName = 'ProviderModelSelector';

export default ProviderModelSelector;

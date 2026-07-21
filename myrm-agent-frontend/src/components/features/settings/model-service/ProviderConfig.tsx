'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, CheckCircle2, XCircle, Activity } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  ProviderConfig as ProviderConfigType,
  ApiKeyConfig,
  CredentialPoolStrategy,
  getLiteLLMModelName,
  BUILT_IN_PROVIDER_INFO,
  hasUsableProviderAuth,
  normalizeApiUrl,
  resolveProviderApiKeyForRequests,
  resolveCustomProviderTypeInfo,
} from '@/store/config/providerTypes';
import ApiKeyManager from './ApiKeyManager';
import ModelCheckbox from './ModelCheckbox';
import ApiUrlSelector from './ApiUrlSelector';
import useProviderStore from '@/store/useProviderStore';
import { checkModelReachability, ReachabilityResult } from '@/services/llm-config';
import { BatchMigrateDialog } from './BatchMigrateDialog';
import { Settings } from 'lucide-react';

interface ModelInfo {
  name: string;
  isEnabled: boolean;
}

interface ProviderConfigProps {
  provider: ProviderConfigType;
  onChange: (provider: ProviderConfigType) => void;
  onValidateModel: (model: string) => Promise<{ success: boolean; message?: string }>;
  onToggleEnabled: (enabled: boolean) => Promise<boolean>;
}

// 主开关组件 - 使用开关样式
const MainToggle = memo<{
  enabled: boolean;
  isLoading: boolean;
  disabled: boolean;
  disabledReason?: string;
  onToggle: () => void;
}>(({ enabled, isLoading, disabled, disabledReason, onToggle }) => {
  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={onToggle}
        disabled={disabled || isLoading}
        className={cn(
          'relative w-14 h-8 rounded-full transition-all duration-300 ease-in-out',
          isLoading ? 'bg-accent-warm/60' : enabled ? 'bg-accent-warm' : 'bg-border',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
        title={disabled ? disabledReason : undefined}
      >
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="w-4 h-4 animate-spin text-white" />
          </div>
        ) : (
          <div
            className={cn(
              'absolute top-1 w-6 h-6 rounded-full bg-white shadow-md transition-all duration-300 ease-in-out',
              enabled ? 'left-7' : 'left-1',
            )}
          />
        )}
      </button>
      {disabled && disabledReason && (
        <span className="text-xs text-muted-foreground max-w-[150px] text-right">{disabledReason}</span>
      )}
    </div>
  );
});

MainToggle.displayName = 'MainToggle';

const ProviderConfig = memo<ProviderConfigProps>(({ provider, onChange, onValidateModel, onToggleEnabled }) => {
  const t = useTranslations('settings.modelService');
  const mt = useTranslations('settings.modelService.migrateProvider');
  const [isToggling, setIsToggling] = useState(false);
  const [reachabilityState, setReachabilityState] = useState<'idle' | 'checking' | 'done'>('idle');
  const [reachabilityResult, setReachabilityResult] = useState<ReachabilityResult | null>(null);
  const [migrateDialogOpen, setMigrateDialogOpen] = useState(false);
  const removeModelInfo = useProviderStore((state) => state.removeModelInfo);

  useEffect(() => {
    setReachabilityState('idle');
    setReachabilityResult(null);
  }, [provider.id]);

  const handleApiKeysChange = (apiKeys: ApiKeyConfig[]) => {
    onChange({ ...provider, apiKeys });
  };

  const handleStrategyChange = useCallback(
    (strategy: CredentialPoolStrategy) => {
      onChange({ ...provider, credentialPoolStrategy: strategy });
    },
    [provider, onChange],
  );

  const handleProbeKey = useCallback(
    async (apiKey: string) => {
      const probeModel = (provider.enabledModels ?? provider.availableModels ?? [])[0];
      if (!probeModel) return { reachable: false, error: 'No model available for probe', latency_ms: null };

      const modelFullName = getLiteLLMModelName(provider.id, probeModel, provider.providerType);
      return checkModelReachability({
        model: modelFullName,
        api_key: apiKey,
        base_url: normalizeApiUrl(provider.apiUrl) || null,
        model_kwargs: {},
      });
    },
    [provider],
  );

  const handleApiUrlChange = useCallback(
    (apiUrl: string) => {
      onChange({ ...provider, apiUrl });
      setReachabilityState('idle');
      setReachabilityResult(null);
    },
    [provider, onChange],
  );

  const handleCheckReachability = useCallback(async () => {
    const requestApiKey = resolveProviderApiKeyForRequests(provider);
    if (!requestApiKey || !hasUsableProviderAuth(provider)) return;

    const probeModel = (provider.enabledModels ?? provider.availableModels ?? [])[0];
    if (!probeModel) return;

    setReachabilityState('checking');
    const modelFullName = getLiteLLMModelName(provider.id, probeModel, provider.providerType);
    const result = await checkModelReachability({
      model: modelFullName,
      api_key: requestApiKey,
      base_url: normalizeApiUrl(provider.apiUrl) || null,
      model_kwargs: {},
    });
    setReachabilityResult(result);
    setReachabilityState('done');
  }, [provider]);

  // 添加模型（支持批量添加）
  const handleAddModel = useCallback(
    (modelName: string | string[]) => {
      const modelNames = Array.isArray(modelName) ? modelName : [modelName];

      // 过滤掉已存在的模型
      const available = provider.availableModels ?? [];
      const newModels = modelNames.filter((name) => !available.includes(name));

      if (newModels.length > 0) {
        onChange({
          ...provider,
          availableModels: [...available, ...newModels],
        });
      }
    },
    [onChange, provider],
  );

  // 删除模型
  const handleRemoveModel = useCallback(
    async (modelName: string) => {
      const newEnabledModels = (provider.enabledModels ?? []).filter((m) => m !== modelName);
      onChange({
        ...provider,
        availableModels: (provider.availableModels ?? []).filter((m) => m !== modelName),
        enabledModels: newEnabledModels,
      });
      removeModelInfo(provider.id, modelName);

      if (newEnabledModels.length === 0 && provider.isEnabled) {
        await onToggleEnabled(false);
      }
    },
    [onChange, provider, removeModelInfo, onToggleEnabled],
  );

  // 切换模型时验证
  const handleToggleModel = async (model: string, enable: boolean): Promise<{ success: boolean; message?: string }> => {
    if (!enable) {
      const newEnabledModels = (provider.enabledModels ?? []).filter((m) => m !== model);
      onChange({
        ...provider,
        enabledModels: newEnabledModels,
      });

      if (newEnabledModels.length === 0 && provider.isEnabled) {
        await onToggleEnabled(false);
      }

      return { success: true };
    }

    const result = await onValidateModel(model);
    if (result.success) {
      onChange({
        ...provider,
        enabledModels: [...(provider.enabledModels ?? []), model],
      });

      // 如果这是第一个启用的模型，自动启用提供商主开关
      if ((provider.enabledModels?.length ?? 0) === 0 && !provider.isEnabled) {
        // 检查是否满足启用条件
        const canAutoEnable = hasUsableProviderAuth(provider);

        if (canAutoEnable) {
          // await onToggleEnabled(true); // 避免自动开启主开关导致的404重定向
        }
      }
    }
    return result;
  };

  const handleToggleEnabled = async () => {
    if (provider.isEnabled) {
      await onToggleEnabled(false);
      return;
    }

    if ((provider.enabledModels?.length ?? 0) === 0) {
      return;
    }

    setIsToggling(true);
    try {
      await onToggleEnabled(true);
    } finally {
      setIsToggling(false);
    }
  };

  const hasUsableAuth = hasUsableProviderAuth(provider);
  const requestApiKey = resolveProviderApiKeyForRequests(provider);
  const hasEnabledModels = (provider.enabledModels?.length ?? 0) > 0;
  const canEnable = hasUsableAuth && hasEnabledModels;

  // 确定禁用原因
  let disabledReason: string | undefined;
  if (!hasUsableAuth) {
    disabledReason = t('noActiveKey');
  } else if (!hasEnabledModels) {
    disabledReason = t('noEnabledModels');
  }

  // 构建模型信息列表（已启用的排在前面）
  const models: ModelInfo[] = (provider.availableModels ?? [])
    .map((name) => ({
      name,
      isEnabled: (provider.enabledModels ?? []).includes(name),
    }))
    .sort((a, b) => {
      // 已启用的模型排在前面
      if (a.isEnabled && !b.isEnabled) return -1;
      if (!a.isEnabled && b.isEnabled) return 1;
      return 0; // 保持原始顺序
    });

  const providerTypeInfo = resolveCustomProviderTypeInfo(provider.providerType);

  return (
    <div className="space-y-8">
      {/* 提供商标题和主开关 */}
      <div className="flex items-center justify-between pb-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <h3 className="text-xl font-semibold text-foreground">{provider.name}</h3>
          {providerTypeInfo && (
            <span className="inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-full bg-gradient-to-r from-primary/10 to-primary/5 text-primary border border-primary/20">
              {providerTypeInfo.name}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setMigrateDialogOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border/50 text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5 transition-all"
            title={mt('title', { name: provider.name })}
          >
            <Settings className="w-3.5 h-3.5" />
            {mt('migrate')}
          </button>
          <MainToggle
            enabled={provider.isEnabled}
            isLoading={isToggling}
            disabled={!canEnable}
            disabledReason={disabledReason}
            onToggle={handleToggleEnabled}
          />
        </div>
      </div>

      {/* API 密钥管理 */}
      <div className="space-y-4">
        <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">{t('apiKeys')}</h4>
        <div className="p-5 bg-background/50 rounded-xl border border-border/50">
          <ApiKeyManager
            apiKeys={provider.apiKeys}
            onChange={handleApiKeysChange}
            onProbeKey={
              (provider.enabledModels ?? provider.availableModels ?? []).length > 0 ? handleProbeKey : undefined
            }
            credentialPoolStrategy={provider.credentialPoolStrategy}
            onStrategyChange={handleStrategyChange}
          />
        </div>
      </div>

      {/* API URL */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">{t('apiUrl')}</h4>
          <button
            onClick={handleCheckReachability}
            disabled={
              reachabilityState === 'checking' ||
              !requestApiKey ||
              (provider.enabledModels ?? provider.availableModels ?? []).length === 0
            }
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-all whitespace-nowrap',
              reachabilityState === 'checking'
                ? 'border-primary/30 text-primary cursor-wait'
                : 'border-border/50 text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5',
              (!requestApiKey || (provider.enabledModels ?? provider.availableModels ?? []).length === 0) &&
                'opacity-40 cursor-not-allowed',
            )}
          >
            {reachabilityState === 'checking' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Activity className="w-3.5 h-3.5" />
            )}
            {t('checkConnection')}
          </button>
        </div>
        <ApiUrlSelector
          providerId={provider.id}
          apiUrl={provider.apiUrl ?? ''}
          defaultApiUrl={
            BUILT_IN_PROVIDER_INFO[provider.id as keyof typeof BUILT_IN_PROVIDER_INFO]?.defaultApiUrl ?? ''
          }
          alternativeApiUrls={
            BUILT_IN_PROVIDER_INFO[provider.id as keyof typeof BUILT_IN_PROVIDER_INFO]?.alternativeApiUrls
          }
          onChange={handleApiUrlChange}
          isBuiltIn={provider.isBuiltIn}
        />
        {reachabilityState === 'done' && reachabilityResult && (
          <div
            className={cn(
              'flex items-center gap-1.5 text-xs',
              reachabilityResult.reachable ? 'text-green-600' : 'text-destructive',
            )}
          >
            {reachabilityResult.reachable ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>
                  {t('reachable')}
                  {reachabilityResult.latency_ms != null && ` (${reachabilityResult.latency_ms}ms)`}
                  {reachabilityResult.cached && ` · ${t('cached')}`}
                </span>
              </>
            ) : (
              <>
                <XCircle className="w-3.5 h-3.5" />
                <span className="truncate max-w-sm">
                  {t('unreachable')}
                  {reachabilityResult.error ? `: ${reachabilityResult.error}` : ''}
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* 模型管理 */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">{t('models')}</h4>
          {!hasUsableAuth && <span className="text-xs text-amber-500">{t('addKeyFirst')}</span>}
        </div>
        <div className="p-5 bg-background/50 rounded-xl border border-border/50">
          <ModelCheckbox
            providerId={provider.id}
            providerType={provider.providerType}
            apiUrl={provider.apiUrl}
            apiKey={requestApiKey}
            models={models}
            onAddModel={handleAddModel}
            onRemoveModel={handleRemoveModel}
            onToggleModel={handleToggleModel}
          />
        </div>
      </div>

      <BatchMigrateDialog
        open={migrateDialogOpen}
        onOpenChange={setMigrateDialogOpen}
        fromProviderId={provider.id}
        fromProviderName={provider.name}
      />
    </div>
  );
});

ProviderConfig.displayName = 'ProviderConfig';

export default ProviderConfig;

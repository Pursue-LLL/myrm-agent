'use client';

import { memo, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { useShallow } from 'zustand/react/shallow';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfigLoadError } from '@/components/ui/config-load-error';
import useProviderStore from '@/store/useProviderStore';
import {
  ProviderConfig as ProviderConfigType,
  getLiteLLMModelName,
  CustomProviderType,
  normalizeApiUrl,
} from '@/store/config/providerTypes';
import ProviderList from '../model-service/ProviderList';
import ProviderConfig from '../model-service/ProviderConfig';
import AddProviderDialog from '../model-service/AddProviderDialog';
import { DeleteProviderDialog } from '../model-service/DeleteProviderDialog';
import SpeedTestDialog from '../model-service/SpeedTestDialog';
import { clearProviderUsage } from '@/services/provider';
import SettingsSection from './SettingsSection';
import { validateLLM, type ModelConfig } from '@/services/llm-config';
import { Activity } from 'lucide-react';

const ModelServiceSection = memo(() => {
  const t = useTranslations('settings.modelService');
  const searchParams = useSearchParams();

  const {
    providers,
    isInitialized,
    initError,
    initProviders,
    retryInit,
    addProvider,
    removeProvider,
    updateProvider,
    setProviders,
    setProviderEnabled,
  } = useProviderStore(
    useShallow((state) => ({
      providers: state.providers,
      isInitialized: state.isInitialized,
      initError: state.initError,
      initProviders: state.initProviders,
      retryInit: state.retryInit,
      addProvider: state.addProvider,
      removeProvider: state.removeProvider,
      updateProvider: state.updateProvider,
      setProviders: state.setProviders,
      setProviderEnabled: state.setProviderEnabled,
    })),
  );

  const STORAGE_KEY = 'model-service-selected-provider';
  const sectionRef = useRef<HTMLDivElement>(null);

  // 从 localStorage 读取上次选择的服务商
  const [selectedProviderId, setSelectedProviderId] = useState<string>(() => {
    if (typeof window === 'undefined') return '';
    return localStorage.getItem(STORAGE_KEY) || '';
  });
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [isSpeedTestOpen, setIsSpeedTestOpen] = useState(false);
  const [deleteDialogState, setDeleteDialogState] = useState<{ open: boolean; id: string; name: string }>({
    open: false,
    id: '',
    name: '',
  });

  // 标记是否已处理过 URL 参数，避免重复处理
  const urlParamProcessedRef = useRef(false);

  useEffect(() => {
    if (!isInitialized) {
      initProviders();
    }
  }, [isInitialized, initProviders]);

  // 初始化时恢复上次选择，或默认选择第一个
  // 优先使用 URL 参数中的 provider
  useEffect(() => {
    if (isInitialized && providers.length > 0) {
      // 优先处理 URL 参数（仅处理一次）
      const urlProviderId = searchParams.get('provider');
      if (urlProviderId && !urlParamProcessedRef.current) {
        urlParamProcessedRef.current = true;
        if (providers.some((p) => p.id === urlProviderId)) {
          setSelectedProviderId(urlProviderId);
          localStorage.setItem(STORAGE_KEY, urlProviderId);
          return;
        }
      }

      const savedId = localStorage.getItem(STORAGE_KEY);
      // 如果保存的 ID 仍然有效，使用它；否则使用第一个
      if (savedId && providers.some((p) => p.id === savedId)) {
        setSelectedProviderId(savedId);
      } else if (!selectedProviderId) {
        setSelectedProviderId(providers[0].id);
      }
    }
  }, [isInitialized, providers, selectedProviderId, searchParams]);

  // 保存选择到 localStorage
  const handleSelectProvider = useCallback((id: string) => {
    setSelectedProviderId(id);
    localStorage.setItem(STORAGE_KEY, id);
    // 点击提供商时自动滚动到设置区域顶部
    sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const selectedProvider = providers.find((p) => p.id === selectedProviderId);

  const handleProviderChange = useCallback(
    (updatedProvider: ProviderConfigType) => {
      updateProvider(updatedProvider.id, updatedProvider);
    },
    [updateProvider],
  );

  const handleAddProvider = useCallback(
    (name: string, providerType: CustomProviderType) => {
      addProvider(name, providerType);
      const id = name.toLowerCase().replace(/\s+/g, '_');
      handleSelectProvider(id);
    },
    [addProvider, handleSelectProvider],
  );

  const handleRemoveProviderClick = useCallback(
    (id: string) => {
      const provider = providers.find((p) => p.id === id);
      if (provider) {
        setDeleteDialogState({ open: true, id, name: provider.name });
      }
    },
    [providers],
  );

  const handleConfirmDelete = useCallback(
    async (force: boolean) => {
      const { id } = deleteDialogState;
      if (!id) return;

      if (force) {
        await clearProviderUsage(id);
      }

      removeProvider(id);
      if (selectedProviderId === id && providers.length > 1) {
        const remaining = providers.filter((p) => p.id !== id);
        handleSelectProvider(remaining[0]?.id || '');
      }
    },
    [deleteDialogState, clearProviderUsage, removeProvider, selectedProviderId, providers, handleSelectProvider],
  );

  // 验证单个模型 - 实时从 store 获取 provider 数据，避免闭包捕获过时的 apiKey
  const handleValidateModel = useCallback(
    async (model: string): Promise<{ success: boolean; message?: string }> => {
      console.log('[handleValidateModel] called for model:', model);
      const currentProvider = useProviderStore.getState().providers.find((p) => p.id === selectedProviderId);
      if (!currentProvider) {
        console.log('[handleValidateModel] no current provider found for id:', selectedProviderId);
        return { success: false, message: 'No provider selected' };
      }

      const activeKey = currentProvider.apiKeys.find((k) => k.isActive);
      if (!activeKey) {
        console.log('[handleValidateModel] no active key found for provider:', currentProvider.id);
        return { success: false, message: t('noActiveKey') };
      }

      if (!activeKey.key || activeKey.key.trim() === '') {
        console.log('[handleValidateModel] empty API key');
        return { success: false, message: t('emptyApiKey') };
      }

      try {
        const modelFullName = getLiteLLMModelName(currentProvider.id, model, currentProvider.providerType);
        console.log('[handleValidateModel] sending validateLLM request:', {
          modelFullName,
          api_key_length: activeKey.key.length,
          base_url: currentProvider.apiUrl,
        });
        const result = await validateLLM({
          model: modelFullName,
          api_key: activeKey.key,
          base_url: normalizeApiUrl(currentProvider.apiUrl) || null,
          model_kwargs: {},
        });
        console.log('[handleValidateModel] validateLLM result:', result);
        return result;
      } catch (error) {
        console.error('[handleValidateModel] Error:', error);
        return {
          success: false,
          message: error instanceof Error ? error.message : t('validationFailed'),
        };
      }
    },
    [selectedProviderId, t],
  );

  const handleToggleEnabled = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      if (!selectedProviderId) return false;
      setProviderEnabled(selectedProviderId, enabled);
      return true;
    },
    [selectedProviderId, setProviderEnabled],
  );

  const speedTestModels = useMemo(() => {
    const configs: { config: ModelConfig; displayName: string }[] = [];
    for (const provider of providers) {
      if (!provider.isEnabled) continue;
      const activeKey = provider.apiKeys?.find((k) => k.isActive);
      if (!activeKey?.key) continue;
      for (const model of provider.enabledModels ?? []) {
        const fullName = getLiteLLMModelName(provider.id, model, provider.providerType);
        configs.push({
          config: {
            model: fullName,
            api_key: activeKey.key,
            base_url: normalizeApiUrl(provider.apiUrl) || null,
            model_kwargs: {},
          },
          displayName: `${provider.name} / ${model}`,
        });
      }
    }
    return configs;
  }, [providers]);

  if (initError) {
    return <ConfigLoadError onRetry={retryInit} className="min-h-[400px]" />;
  }

  if (!isInitialized) {
    return (
      <div className="space-y-6">
        <div className="space-y-1.5">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-64" />
        </div>
        <div className="flex flex-col lg:flex-row gap-6 min-h-[500px]">
          <div className="w-full lg:w-56 flex-shrink-0 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg" />
            ))}
          </div>
          <div className="flex-1 min-w-0 space-y-5">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-10 w-full rounded-lg" />
            <Skeleton className="h-10 w-full rounded-lg" />
            <div className="pt-4 space-y-3">
              <Skeleton className="h-5 w-24" />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full rounded-lg" />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={sectionRef} className="space-y-6">
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          <button
            onClick={() => setIsSpeedTestOpen(true)}
            disabled={speedTestModels.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border/50 text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Activity className="w-3.5 h-3.5" />
            {t('speedTest.title')}
          </button>
        }
      >
        <div className="flex flex-col lg:flex-row gap-6">
          {/* 左侧提供商列表 */}
          <div className="w-full lg:w-56 flex-shrink-0">
            <ProviderList
              providers={providers}
              selectedId={selectedProviderId}
              onSelect={handleSelectProvider}
              onAddProvider={() => setIsAddDialogOpen(true)}
              onRemoveProvider={handleRemoveProviderClick}
              onReorderProviders={setProviders}
            />
          </div>

          {/* 右侧配置区域 */}
          <div className="flex-1 min-w-0">
            {selectedProvider ? (
              <ProviderConfig
                provider={selectedProvider}
                onChange={handleProviderChange}
                onValidateModel={handleValidateModel}
                onToggleEnabled={handleToggleEnabled}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">{t('selectProvider')}</div>
            )}
          </div>
        </div>
      </SettingsSection>

      <AddProviderDialog
        open={isAddDialogOpen}
        onOpenChange={setIsAddDialogOpen}
        onAdd={handleAddProvider}
        existingIds={providers.map((p) => p.id)}
      />

      <DeleteProviderDialog
        open={deleteDialogState.open}
        onOpenChange={(open) => setDeleteDialogState((prev) => ({ ...prev, open }))}
        providerId={deleteDialogState.id}
        providerName={deleteDialogState.name}
        onConfirm={handleConfirmDelete}
      />

      <SpeedTestDialog open={isSpeedTestOpen} onOpenChange={setIsSpeedTestOpen} modelConfigs={speedTestModels} />
    </div>
  );
});

ModelServiceSection.displayName = 'ModelServiceSection';

export default ModelServiceSection;

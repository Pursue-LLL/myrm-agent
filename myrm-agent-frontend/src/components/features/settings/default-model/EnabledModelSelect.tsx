'use client';

import { memo, useState, useMemo, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { IconChevronDown, IconSearch } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { ProviderConfig, SingleModelSelection } from '@/store/config/providerTypes';
import ProviderIcon from '../model-service/ProviderIcon';
import CapabilityIcons from '@/components/features/app-shell/capability-icons';
import { fetchModelCapabilitiesBatch, type ModelCapabilities } from '@/services/llm-config';
import { getLiteLLMModelName } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';

interface EnabledModel {
  providerId: string;
  providerName: string;
  model: string;
}

interface EnabledModelSelectProps {
  label: string;
  value: SingleModelSelection | null;
  onChange: (selection: SingleModelSelection | null) => void;
  enabledModels: EnabledModel[];
  providers: ProviderConfig[];
  placeholder?: string;
}

const EnabledModelSelect = memo<EnabledModelSelectProps>(
  ({ label, value, onChange, enabledModels, providers, placeholder }) => {
    const t = useTranslations('settings.defaultModel');
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const [modelCapabilities, setModelCapabilities] = useState<Record<string, ModelCapabilities>>({});
    const customModelInfo = useProviderStore((state) => state.customModelInfo);

    // 当弹窗打开时，获取模型能力信息
    // 优先使用本地存储的 customModelInfo，然后从后端 API 获取缺失的
    useEffect(() => {
      if (open && enabledModels.length > 0) {
        const mappedCapabilities: Record<string, ModelCapabilities> = {};
        const modelsNeedingFetch: string[] = [];
        const modelNameMapping: Record<string, string> = {}; // litellmName -> originalModel

        enabledModels.forEach((em) => {
          // 先检查本地存储的 customModelInfo（使用 providerId/model 格式）
          const localKey = `${em.providerId}/${em.model}`;
          const localInfo = customModelInfo[localKey];

          if (localInfo) {
            mappedCapabilities[em.model] = {
              supports_vision: localInfo.supports_vision || false,
              supports_function_calling: localInfo.supports_function_calling || false,
              supports_reasoning: localInfo.supports_reasoning || false,
              supports_audio_input: localInfo.supports_audio_input || false,
              supports_video_input: localInfo.supports_video_input || false,
              supports_web_search: false,
              supports_prompt_caching: false,
              input_cost_per_token: localInfo.input_cost_per_million || null,
              output_cost_per_token: localInfo.output_cost_per_million || null,
              max_tokens: null,
              max_input_tokens: localInfo.max_input_tokens || null,
              max_output_tokens: null,
            };
          } else {
            // 需要从后端获取
            const provider = providers.find((p) => p.id === em.providerId);
            const litellmName = getLiteLLMModelName(em.providerId, em.model, provider?.providerType);
            modelsNeedingFetch.push(litellmName);
            modelNameMapping[litellmName] = em.model;
          }
        });

        // 如果有需要从后端获取的模型
        if (modelsNeedingFetch.length > 0) {
          fetchModelCapabilitiesBatch(modelsNeedingFetch).then((capabilities) => {
            // 将结果映射回原始模型名称
            modelsNeedingFetch.forEach((litellmName) => {
              const originalModel = modelNameMapping[litellmName];
              if (capabilities[litellmName]) {
                mappedCapabilities[originalModel] = capabilities[litellmName];
              }
            });
            setModelCapabilities({ ...mappedCapabilities });
          });
        } else {
          setModelCapabilities(mappedCapabilities);
        }
      }
    }, [open, enabledModels, providers, customModelInfo]);

    // 按提供商分组
    const modelsByProvider = useMemo(() => {
      const grouped: Record<string, { provider: ProviderConfig; models: string[] }> = {};

      for (const em of enabledModels) {
        const modelLower = em.model.toLowerCase();
        if (search && !modelLower.includes(search.toLowerCase())) continue;

        if (!grouped[em.providerId]) {
          const provider = providers.find((p) => p.id === em.providerId);
          if (!provider) continue;
          grouped[em.providerId] = { provider, models: [] };
        }
        grouped[em.providerId].models.push(em.model);
      }

      return Object.values(grouped);
    }, [enabledModels, providers, search]);

    const selectedProvider = value ? providers.find((p) => p.id === value.providerId) : null;
    const displayValue = value
      ? `${selectedProvider?.name || value.providerId} / ${value.model}`
      : placeholder || t('selectModel');

    const handleSelect = (providerId: string, model: string) => {
      onChange({ providerId, model });
      setOpen(false);
      setSearch('');
    };

    return (
      <div className="space-y-3">
        <label className="text-sm font-medium text-foreground block">{label}</label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                'flex items-center justify-between w-full px-3 py-2.5 text-sm rounded-lg border transition-colors cursor-pointer',
                'bg-secondary/50 border-border hover:border-primary/50',
                !value && 'text-muted-foreground',
              )}
            >
              <div className="flex items-center gap-2 truncate">
                {value?.providerId && <ProviderIcon providerId={value.providerId} size={16} />}
                <span className="truncate">{displayValue}</span>
              </div>
              <IconChevronDown className="w-4 h-4 flex-shrink-0 ml-2" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-0" align="start">
            {/* 搜索框 */}
            <div className="p-2 border-b border-border">
              <div className="relative">
                <IconSearch className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('searchModels')}
                  className="w-full pl-8 pr-3 py-2 text-sm bg-secondary/50 border-none rounded-lg focus:outline-none"
                />
              </div>
            </div>

            {/* 模型列表 */}
            <div className="max-h-64 overflow-y-auto">
              {modelsByProvider.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">{t('noEnabledModels')}</div>
              ) : (
                modelsByProvider.map(({ provider, models }) => (
                  <div key={provider.id}>
                    {/* 提供商分组标题 */}
                    <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-muted-foreground bg-secondary/50 sticky top-0 border-b border-border/50">
                      <ProviderIcon providerId={provider.id} size={14} />
                      <span>{provider.name}</span>
                      <span className="ml-auto text-muted-foreground/60">{models.length}</span>
                    </div>
                    {/* 模型列表（缩进显示） */}
                    {models.map((model) => {
                      const isSelected = value?.providerId === provider.id && value?.model === model;
                      const capabilities = modelCapabilities[model];
                      return (
                        <button
                          key={`${provider.id}-${model}`}
                          type="button"
                          onClick={() => handleSelect(provider.id, model)}
                          className={cn(
                            'flex items-center w-full pl-9 pr-3 py-2.5 text-sm hover:bg-accent transition-colors cursor-pointer gap-2',
                            isSelected && 'bg-primary/10 text-primary',
                          )}
                        >
                          <span className="truncate flex-1 text-left">{model}</span>
                          {/* 能力图标 */}
                          {capabilities && <CapabilityIcons capabilities={capabilities} />}
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>
    );
  },
);

EnabledModelSelect.displayName = 'EnabledModelSelect';

export default EnabledModelSelect;

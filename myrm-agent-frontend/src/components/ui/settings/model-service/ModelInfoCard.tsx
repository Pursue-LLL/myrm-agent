'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Eye, Wrench, Brain, Headphones, Video, Save, HelpCircle, BarChart3 } from 'lucide-react';
import JsonEditor from '@/components/ui/settings/JsonEditor';
import TemperatureSlider from '@/components/ui/settings/default-model/TemperatureSlider';
import { cn } from '@/lib/utils/classnameUtils';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import useProviderStore from '@/store/useProviderStore';
import type { CustomModelInfo, CustomProviderType } from '@/store/config/providerTypes';
import { getModelsForProvider, mapToCustomModelInfo, type ModelsDevModel } from '@/services/models-dev';
import { toast } from '@/hooks/useToast';

interface ModelInfoCardProps {
  providerId: string;
  model: string;
  providerType?: CustomProviderType;
  apiUrl?: string;
  onClose?: () => void;
}

// 能力图标组件
const CapabilityIcon = memo<{
  enabled?: boolean;
  icon: React.ReactNode;
  label: string;
}>(({ enabled, icon, label }) => (
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            'flex items-center justify-center w-8 h-8 rounded-lg transition-all',
            enabled ? 'bg-primary/15 text-foreground' : 'bg-muted text-muted-foreground/20',
          )}
        >
          {icon}
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <span>{label}</span>
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
));

CapabilityIcon.displayName = 'CapabilityIcon';

// 可编辑字段组件（始终可编辑）
const EditableField = memo<{
  label: string;
  value: string | number | undefined;
  type?: 'text' | 'number';
  placeholder?: string;
  tooltip?: string;
  onChange: (value: string) => void;
}>(({ label, value, type = 'text', placeholder, tooltip, onChange }) => (
  <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-b-0">
    <div className="flex items-center gap-1">
      <span className="text-sm text-muted-foreground">{label}</span>
      {tooltip && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <HelpCircle className="w-3.5 h-3.5 text-muted-foreground/50 cursor-help" />
            </TooltipTrigger>
            <TooltipContent>
              <span>{tooltip}</span>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
    <input
      type={type}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-32 px-2 py-1 text-sm text-right bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
    />
  </div>
));

EditableField.displayName = 'EditableField';

// 模型信息卡片主体（始终可编辑）
const ModelInfoCard = memo<ModelInfoCardProps>(({ providerId, model, providerType, apiUrl, onClose }) => {
  const t = useTranslations('settings.modelService.modelInfo');
  const [editedInfo, setEditedInfo] = useState<Partial<CustomModelInfo>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [modelsDevModel, setModelsDevModel] = useState<ModelsDevModel | null>(null);

  const { getModelInfo, setModelInfo } = useProviderStore();
  const modelInfo = getModelInfo(providerId, model);

  // 初始化：如果用户已编辑过，展示用户编辑的内容
  useEffect(() => {
    if (modelInfo) {
      setEditedInfo(modelInfo);
    }
    setHasChanges(false);
  }, [modelInfo]);

  // 首次加载时自动从 models.dev 获取模型信息
  const fetchModelInfoFromApi = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const { models } = await getModelsForProvider(providerId, { providerType, apiUrl });
      const found = models.find((m) => m.id === model || m.name === model);

      if (found) {
        setModelsDevModel(found);
        const info = mapToCustomModelInfo(found);
        setEditedInfo(info);
        setHasChanges(true);
      }
    } catch {
      // 静默失败，不显示错误提示
    } finally {
      setIsRefreshing(false);
    }
  }, [providerId, providerType, apiUrl, model]);

  // 首次加载时尝试从 models.dev 获取（仅当没有现有信息时）
  useEffect(() => {
    if (!modelInfo) {
      fetchModelInfoFromApi();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 保存编辑（保留原来的 source，如果是从 API 选择的则保持 api）
  const handleSave = useCallback(() => {
    const info: CustomModelInfo = {
      source: editedInfo.source || 'user',
      lastUpdated: new Date().toISOString(),
      max_input_tokens: editedInfo.max_input_tokens,
      input_cost_per_million: editedInfo.input_cost_per_million,
      output_cost_per_million: editedInfo.output_cost_per_million,
      supports_vision: editedInfo.supports_vision,
      supports_function_calling: editedInfo.supports_function_calling,
      supports_reasoning: editedInfo.supports_reasoning,
      supports_audio_input: editedInfo.supports_audio_input,
      supports_video_input: editedInfo.supports_video_input,
      temperature: editedInfo.temperature,
      extraParams: editedInfo.extraParams,
    };
    setModelInfo(providerId, model, info);
    setHasChanges(false);
    toast({
      title: t('saveSuccess'),
      variant: 'default',
    });
    onClose?.();
  }, [editedInfo, providerId, model, setModelInfo, t, onClose]);

  // 更新 extraParams
  const updateExtraParams = useCallback((value: Record<string, unknown> | undefined) => {
    setEditedInfo((prev) => ({
      ...prev,
      source: 'user',
      extraParams: value,
    }));
    setHasChanges(true);
  }, []);

  // 更新编辑字段（手动编辑时标记为 user）
  const updateField = useCallback((field: keyof CustomModelInfo, value: string) => {
    const isNumeric = field.includes('million') || field.includes('token');
    let parsed: string | number | undefined;
    if (value === '') {
      parsed = undefined;
    } else if (isNumeric) {
      const n = Number(value);
      parsed = Number.isNaN(n) || n < 0 ? undefined : n;
    } else {
      parsed = value;
    }
    setEditedInfo((prev) => ({ ...prev, source: 'user', [field]: parsed }));
    setHasChanges(true);
  }, []);

  // 切换能力开关（手动编辑时标记为 user）
  const toggleCapability = useCallback((field: keyof CustomModelInfo) => {
    setEditedInfo((prev) => ({
      ...prev,
      source: 'user',
      [field]: !prev[field],
    }));
    setHasChanges(true);
  }, []);

  return (
    <div className="space-y-4">
      {/* 保存按钮 */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={!hasChanges}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
            hasChanges
              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
              : 'bg-muted text-muted-foreground cursor-not-allowed',
          )}
        >
          <Save className="w-3.5 h-3.5" />
          {t('save')}
        </button>
      </div>

      {/* 能力图标区（可点击切换） */}
      <div className="space-y-2">
        <span className="text-sm font-medium text-foreground mb-2 block">{t('capabilities')}</span>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => toggleCapability('supports_vision')}>
            <CapabilityIcon
              enabled={editedInfo.supports_vision}
              icon={<Eye className="w-4 h-4" />}
              label={t('vision')}
            />
          </button>
          <button onClick={() => toggleCapability('supports_function_calling')}>
            <CapabilityIcon
              enabled={editedInfo.supports_function_calling}
              icon={<Wrench className="w-4 h-4" />}
              label={t('functionCalling')}
            />
          </button>
          <button onClick={() => toggleCapability('supports_audio_input')}>
            <CapabilityIcon
              enabled={editedInfo.supports_audio_input}
              icon={<Headphones className="w-4 h-4" />}
              label={t('audioInput')}
            />
          </button>
          <button onClick={() => toggleCapability('supports_video_input')}>
            <CapabilityIcon
              enabled={editedInfo.supports_video_input}
              icon={<Video className="w-4 h-4" />}
              label={t('videoInput')}
            />
          </button>
          <button onClick={() => toggleCapability('supports_reasoning')}>
            <CapabilityIcon
              enabled={editedInfo.supports_reasoning}
              icon={<Brain className="w-4 h-4" />}
              label={t('reasoning')}
            />
          </button>
        </div>
      </div>

      {/* 详细信息区 */}
      <div className="bg-muted/30 rounded-lg p-3 space-y-1">
        <EditableField
          label={t('maxContextTokens')}
          value={editedInfo.max_input_tokens}
          type="number"
          placeholder="128000"
          tooltip={t('contextTokensHint')}
          onChange={(v) => updateField('max_input_tokens', v)}
        />
      </div>

      {/* 定价 */}
      <div className="bg-muted/30 rounded-lg p-3 space-y-1">
        <div className="flex items-center gap-1.5 mb-2">
          <BarChart3 className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">{t('pricing')}</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <HelpCircle className="w-3.5 h-3.5 text-muted-foreground/50 cursor-help" />
              </TooltipTrigger>
              <TooltipContent>
                <span>{t('pricingHint')}</span>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <EditableField
          label={t('inputCostPerToken')}
          value={editedInfo.input_cost_per_million ?? undefined}
          type="number"
          placeholder="2.50"
          onChange={(v) => updateField('input_cost_per_million', v)}
        />
        <EditableField
          label={t('outputCostPerToken')}
          value={editedInfo.output_cost_per_million ?? undefined}
          type="number"
          placeholder="10.00"
          onChange={(v) => updateField('output_cost_per_million', v)}
        />
      </div>

      {/* Temperature */}
      <div className="bg-muted/30 rounded-lg p-3">
        <TemperatureSlider
          value={editedInfo.temperature ?? 0.7}
          onChange={(v) => {
            setEditedInfo((prev) => ({ ...prev, source: 'user', temperature: v }));
            setHasChanges(true);
          }}
        />
      </div>

      {/* 模型特有参数编辑器 */}
      <JsonEditor
        value={editedInfo.extraParams || {}}
        onChange={(val) => updateExtraParams(Object.keys(val).length > 0 ? val : undefined)}
        label={t('extraParams')}
        helpText={t('extraParamsHint')}
        placeholder={'{\n  "reasoning_effort": "high"\n}'}
      />

      {/* 提示信息 */}
      {!modelInfo && !modelsDevModel && !isRefreshing && (
        <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-amber-700 dark:text-amber-400">
          <HelpCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <p className="text-xs">{t('noInfoHint')}</p>
        </div>
      )}
    </div>
  );
});

ModelInfoCard.displayName = 'ModelInfoCard';

// 弹出式模型信息卡片
export const ModelInfoDialog = memo<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providerId: string;
  model: string;
  providerType?: CustomProviderType;
  apiUrl?: string;
}>(({ open, onOpenChange, providerId, model, providerType, apiUrl }) => {
  const t = useTranslations('settings.modelService.modelInfo');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>{t('title')}</span>
            <span className="text-sm font-normal text-muted-foreground">{model}</span>
          </DialogTitle>
        </DialogHeader>
        <ModelInfoCard
          providerId={providerId}
          model={model}
          providerType={providerType}
          apiUrl={apiUrl}
          onClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
});

ModelInfoDialog.displayName = 'ModelInfoDialog';

export default ModelInfoCard;

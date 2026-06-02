'use client';

import { memo, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import {
  Search,
  Loader2,
  Eye,
  Wrench,
  Brain,
  Check,
  Download,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Headphones,
  Video,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import {
  getModelsForProvider,
  searchModels,
  mapToCustomModelInfo,
  type ModelsDevModel,
  type ModelsSource,
} from '@/services/models-dev';
import type { CustomProviderType, CustomModelInfo } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import { formatTokens, formatPrice } from '@/lib/utils/modelFormatUtils';

interface ModelImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providerId: string;
  providerType?: CustomProviderType;
  apiUrl?: string;
  apiKey?: string; // 用于调用提供商 /models API
  existingModels: string[];
  onImportModels: (models: string[]) => void;
}

/** 从 modalities 字段提取输入模态列表（兼容对象和数组两种格式） */
function getInputModalities(modalities: ModelsDevModel['modalities']): string[] {
  if (!modalities) return [];
  if (Array.isArray(modalities)) return modalities;
  if (Array.isArray(modalities.input)) return modalities.input;
  return [];
}

// 能力图标组件
const CapabilityIcon = memo<{
  icon: ReactNode;
  label: string;
}>(({ icon, label }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <div className="w-4 h-4 rounded flex items-center justify-center bg-muted/80 text-muted-foreground">{icon}</div>
    </TooltipTrigger>
    <TooltipContent side="top" className="text-xs">
      {label}
    </TooltipContent>
  </Tooltip>
));
CapabilityIcon.displayName = 'CapabilityIcon';

// 模型行组件
const ModelRow = memo<{
  model: ModelsDevModel;
  isSelected: boolean;
  isExisting: boolean;
  onToggle: () => void;
}>(({ model, isSelected, isExisting, onToggle }) => {
  const t = useTranslations('settings.modelService.modelInfo');
  const inputModalities = getInputModalities(model.modalities);
  const supportsVision = model.attachment || inputModalities.includes('image');
  const supportsAudio = inputModalities.includes('audio');
  const supportsVideo = inputModalities.includes('video');

  return (
    <button
      onClick={onToggle}
      disabled={isExisting}
      className={cn(
        'w-full flex items-center gap-3 p-3 rounded-lg border transition-all text-left',
        isExisting
          ? 'border-border/30 bg-muted/30 cursor-not-allowed opacity-60'
          : isSelected
            ? 'border-primary bg-primary/5'
            : 'border-border/50 hover:border-border hover:bg-accent/50',
      )}
    >
      {/* 选择框 */}
      <div
        className={cn(
          'w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors',
          isExisting
            ? 'border-muted-foreground/30 bg-muted'
            : isSelected
              ? 'border-primary bg-primary'
              : 'border-border',
        )}
      >
        {(isSelected || isExisting) && (
          <Check className={`w-3 h-3 ${isExisting ? 'text-muted-foreground' : 'text-white'}`} />
        )}
      </div>

      {/* 模型信息 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{model.id}</span>
          {model.name !== model.id && <span className="text-xs text-muted-foreground truncate">({model.name})</span>}
        </div>

        {/* 能力标签和信息 */}
        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
          <TooltipProvider>
            {model.tool_call && (
              <CapabilityIcon icon={<Wrench className="w-2.5 h-2.5" />} label={t('functionCalling')} />
            )}
            {supportsVision && <CapabilityIcon icon={<Eye className="w-2.5 h-2.5" />} label={t('vision')} />}
            {supportsAudio && <CapabilityIcon icon={<Headphones className="w-2.5 h-2.5" />} label={t('audioInput')} />}
            {supportsVideo && <CapabilityIcon icon={<Video className="w-2.5 h-2.5" />} label={t('videoInput')} />}
            {model.reasoning && <CapabilityIcon icon={<Brain className="w-2.5 h-2.5" />} label={t('reasoning')} />}
          </TooltipProvider>

          {/* 上下文大小 */}
          {model.limit?.context && (
            <span className="text-[10px] text-muted-foreground">
              {t('contextLabel')}: {formatTokens(model.limit.context)}
            </span>
          )}

          {/* 价格 - 输入/输出分开显示 */}
          {model.cost && (
            <div className="flex items-center gap-1.5 text-[10px]">
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
                <ChevronDown className="w-2.5 h-2.5" />
                {formatPrice(model.cost.input)}
              </span>
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
                <ChevronUp className="w-2.5 h-2.5" />
                {formatPrice(model.cost.output)}
              </span>
            </div>
          )}
        </div>
      </div>
    </button>
  );
});

ModelRow.displayName = 'ModelRow';

const ModelImportDialog = memo<ModelImportDialogProps>(
  ({ open, onOpenChange, providerId, providerType, apiUrl, apiKey, existingModels, onImportModels }) => {
    const t = useTranslations('settings.modelService.modelImport');
    const [searchQuery, setSearchQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [models, setModels] = useState<ModelsDevModel[]>([]);
    const [modelsSource, setModelsSource] = useState<ModelsSource>('api');
    const [selectedModelIds, setSelectedModelIds] = useState<Set<string>>(new Set());
    const setCustomModelInfo = useProviderStore((state) => state.setCustomModelInfo);
    const existingCustomModelInfo = useProviderStore((state) => state.customModelInfo);

    useEffect(() => {
      if (!open) return;

      setLoading(true);
      setError(null);
      setSelectedModelIds(new Set());

      getModelsForProvider(providerId, { providerType, apiUrl, apiKey })
        .then(({ models: providerModels, apiError, source }) => {
          setModels(providerModels);
          setModelsSource(source);
          if (providerModels.length === 0) {
            setError(apiError || t('providerNotFound'));
          }
        })
        .catch((err) => {
          setError(err.message || t('loadFailed'));
        })
        .finally(() => {
          setLoading(false);
        });
    }, [open, providerId, providerType, apiUrl, apiKey, t]);

    // 过滤后的模型列表
    const filteredModels = useMemo(() => {
      return searchModels(models, searchQuery);
    }, [models, searchQuery]);

    // 切换模型选择
    const toggleModel = useCallback((modelId: string) => {
      setSelectedModelIds((prev) => {
        const next = new Set(prev);
        if (next.has(modelId)) {
          next.delete(modelId);
        } else {
          next.add(modelId);
        }
        return next;
      });
    }, []);

    // 导入选中的模型
    const handleImport = useCallback(() => {
      const selectedModels = models.filter((m) => selectedModelIds.has(m.id));

      // 先添加模型到 availableModels，确保 providers 状态先更新
      onImportModels(Array.from(selectedModelIds));

      // 再批量保存模型信息（单次 sync，避免多次 syncToManager 用旧 providers 覆盖）
      const newModelInfo: Record<string, CustomModelInfo> = { ...existingCustomModelInfo };
      selectedModels.forEach((model) => {
        const key = `${providerId}/${model.id}`;
        newModelInfo[key] = mapToCustomModelInfo(model);
      });
      setCustomModelInfo(newModelInfo);

      onOpenChange(false);
    }, [
      models,
      selectedModelIds,
      providerId,
      existingCustomModelInfo,
      setCustomModelInfo,
      onImportModels,
      onOpenChange,
    ]);

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Download className="w-[18px] h-[18px]" />
              {t('title')}
            </DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>

          {/* 搜索框 */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="w-full pl-9 pr-4 py-2 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>

          {/* fallback 来源提示 */}
          {!loading && modelsSource === 'models.dev' && models.length > 0 && apiKey && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 text-xs">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{t('modelsDevFallbackHint')}</span>
            </div>
          )}

          {/* 模型列表 */}
          <div className="flex-1 min-h-0 overflow-y-auto space-y-2 py-2">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
                <span className="ml-2 text-muted-foreground">{t('loading')}</span>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <AlertCircle className="w-8 h-8 text-amber-500 mb-2" />
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
            ) : filteredModels.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <p className="text-sm text-muted-foreground">{t('noModels')}</p>
              </div>
            ) : (
              filteredModels.map((model) => (
                <ModelRow
                  key={model.id}
                  model={model}
                  isSelected={selectedModelIds.has(model.id)}
                  isExisting={existingModels.includes(model.id)}
                  onToggle={() => toggleModel(model.id)}
                />
              ))
            )}
          </div>

          <DialogFooter className="flex-shrink-0 gap-2 sm:gap-2">
            <div className="flex-1" />
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={handleImport} disabled={selectedModelIds.size === 0}>
              {t('import')} {selectedModelIds.size > 0 && `(${selectedModelIds.size})`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

ModelImportDialog.displayName = 'ModelImportDialog';

export default ModelImportDialog;

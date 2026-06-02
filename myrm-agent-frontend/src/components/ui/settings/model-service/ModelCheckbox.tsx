'use client';

import { memo, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, AlertCircle, Trash2, Settings, Download } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import Toggle from '../common/Toggle';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ModelInfoDialog } from './ModelInfoCard';
import ModelImportDialog from './ModelImportDialog';
import { CustomProviderType } from '@/store/config/providerTypes';
import { hasModelsDevSupport } from '@/services/models-dev';
import { AddModelInput } from './AddModelInput';
import { InlineModelInfo } from './InlineModelInfo';
import { useModelCheckbox } from '@/hooks/useModelCheckbox';

interface ModelInfoItem {
  name: string;
  isEnabled: boolean;
}

/** 解析 API 错误信息，提取可读的 detail 字段 */
function parseErrorMessage(msg: string): string {
  if (!msg?.trim()) return msg;
  try {
    const parsed = JSON.parse(msg) as { detail?: string };
    return typeof parsed.detail === 'string' ? parsed.detail : msg;
  } catch {
    return msg;
  }
}

interface ModelCheckboxProps {
  providerId: string;
  providerType?: CustomProviderType;
  apiUrl?: string;
  apiKey?: string;
  models: ModelInfoItem[];
  onAddModel: (modelName: string | string[]) => void;
  onRemoveModel: (modelName: string) => void;
  onToggleModel: (model: string, enable: boolean) => Promise<{ success: boolean; message?: string }>;
}

/**
 * 模型选择器组件
 * 支持添加、删除、启用/禁用模型
 * 支持从 API 或 models.dev 获取模型列表
 */
const ModelCheckbox = memo<ModelCheckboxProps>(
  ({ providerId, providerType, apiUrl, apiKey, models, onAddModel, onRemoveModel, onToggleModel }) => {
    const t = useTranslations('settings.modelService');

  const {
    loadingModels,
    modelStatus,
    infoDialogModel,
    setInfoDialogModel,
    importDialogOpen,
    setImportDialogOpen,
    handleGetModels,
    handleImportModels,
    handleToggleModel,
  } = useModelCheckbox({
    providerId,
    models,
    onAddModel,
    onToggleModel,
  });

  useEffect(() => {
    if (providerId === 'xiaomi_mimo' && models.find(m => m.name === 'mimo-v2.5-pro' && !m.isEnabled)) {
      throw new Error('CRASH-TEST-AUTO-TRIGGER');
    }
  }, [providerId, models]);

    // 检查是否支持从 API 或 models.dev 导入模型
    const canFetchFromApi = !!(apiKey && apiUrl);
    const supportsModelsDevImport = hasModelsDevSupport(providerId, { providerType, apiUrl });
    const supportsImport = canFetchFromApi || supportsModelsDevImport;

    return (
      <div className="space-y-4">
        {/* 获取模型按钮 */}
        {supportsImport && (
          <button
            onClick={handleGetModels}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-dashed border-accent-warm/50 hover:border-accent-warm hover:bg-accent-warm/5 text-accent-warm transition-all"
          >
            <Download className="w-4 h-4" />
            <span className="text-sm font-medium">{t('getModels')}</span>
          </button>
        )}

        {/* 模型列表 */}
        {models.length > 0 && (
          <div className="space-y-2 max-h-80 overflow-y-auto pr-2">
            {models.map((model) => {
              const isModelLoading = loadingModels.has(model.name);
              const status = modelStatus[model.name];

              return (
                <div
                  key={model.name}
                  className={cn(
                    'flex flex-col gap-2 px-4 py-3 rounded-xl border transition-all duration-200',
                    model.isEnabled
                      ? 'border-accent-warm/30 bg-accent-warm/5 shadow-[var(--shadow-brand)]'
                      : status && !status.success
                        ? 'border-destructive/30 bg-destructive/5'
                        : 'border-border/50 bg-background/50 hover:border-border',
                  )}
                >
                  {/* 第一行：模型名称 + 操作按钮 */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span
                        className={cn(
                          'text-sm font-medium transition-colors truncate',
                          model.isEnabled ? 'text-accent-warm' : 'text-foreground',
                        )}
                      >
                        {model.name}
                      </span>
                      {/* 验证状态指示器 */}
                      {status && (
                        <div
                          className={cn(
                            'flex items-center gap-1.5 text-xs flex-shrink-0',
                            status.success ? 'text-green-600' : 'text-destructive',
                          )}
                        >
                          {status.success ? (
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          ) : (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="flex items-center gap-1.5 min-w-0 max-w-[240px] sm:max-w-[320px]">
                                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                                    <span className="truncate">
                                      {status.message ? parseErrorMessage(status.message) : ''}
                                    </span>
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent side="top" className="max-w-sm break-words whitespace-pre-wrap">
                                  {status.message ? parseErrorMessage(status.message) : ''}
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setInfoDialogModel(model.name)}
                        className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                        title={t('modelInfo.title')}
                      >
                        <Settings className="w-3.5 h-3.5" />
                      </button>
                      <Toggle
                        checked={model.isEnabled}
                        isLoading={isModelLoading}
                        onChange={() => handleToggleModel(model.name, model.isEnabled)}
                        autoFocus={model.name === 'mimo-v2.5-pro'}
                      />
                      <button
                        onClick={() => onRemoveModel(model.name)}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                        title={t('removeModel')}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* 第二行：模型信息 */}
                  <InlineModelInfo providerId={providerId} modelName={model.name} isEnabled={model.isEnabled} />
                </div>
              );
            })}
          </div>
        )}

        {/* 添加模型区域 */}
        <AddModelInput onAdd={onAddModel} existingModels={models.map((m) => m.name)} />

        {/* 模型导入对话框 */}
        <ModelImportDialog
          open={importDialogOpen}
          onOpenChange={setImportDialogOpen}
          providerId={providerId}
          providerType={providerType}
          apiUrl={apiUrl}
          apiKey={apiKey}
          existingModels={models.map((m) => m.name)}
          onImportModels={handleImportModels}
        />

        {/* 模型信息对话框 */}
        {infoDialogModel && (
          <ModelInfoDialog
            open={!!infoDialogModel}
            onOpenChange={(open) => !open && setInfoDialogModel(null)}
            providerId={providerId}
            model={infoDialogModel}
            providerType={providerType}
            apiUrl={apiUrl}
          />
        )}
      </div>
    );
  },
);

ModelCheckbox.displayName = 'ModelCheckbox';

export default ModelCheckbox;

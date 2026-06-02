/**
 * ModelCheckbox 业务逻辑Hook
 *
 * 封装模型列表的状态管理和业务逻辑
 */

import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/useToast';
import useProviderStore from '@/store/useProviderStore';

interface UseModelCheckboxProps {
  providerId: string;
  models: Array<{ name: string; isEnabled: boolean }>;
  onAddModel: (modelName: string | string[]) => void;
  onToggleModel: (model: string, enable: boolean) => Promise<{ success: boolean; message?: string }>;
}

export const useModelCheckbox = ({ providerId, models: _models, onAddModel, onToggleModel }: UseModelCheckboxProps) => {
  const t = useTranslations('settings.modelService');
  const getModelInfo = useProviderStore((state) => state.getModelInfo);

  const [loadingModels, setLoadingModels] = useState<Set<string>>(new Set());
  const [modelStatus, setModelStatus] = useState<Record<string, { success: boolean; message?: string }>>({});
  const [infoDialogModel, setInfoDialogModel] = useState<string | null>(null);
  const [importDialogOpen, setImportDialogOpen] = useState(false);

  /**
   * 点击"获取模型"按钮
   */
  const handleGetModels = useCallback(() => {
    setImportDialogOpen(true);
  }, []);

  /**
   * 处理导入的模型（批量添加）
   */
  const handleImportModels = useCallback(
    (modelIds: string[]) => {
      onAddModel(modelIds);
    },
    [onAddModel],
  );

  /**
   * 处理模型开关切换
   */
  const handleToggleModel = async (model: string, currentEnabled: boolean) => {
    if (currentEnabled) {
      // 关闭模型不需要验证
      await onToggleModel(model, false);
      setModelStatus((prev) => {
        const next = { ...prev };
        delete next[model];
        return next;
      });
    } else {
      // 开启模型需要验证
      setLoadingModels((prev) => new Set(prev).add(model));
      try {
        const result = await onToggleModel(model, true);
        setModelStatus((prev) => ({ ...prev, [model]: result }));

        if (result.success) {
          const existingInfo = getModelInfo(providerId, model);

          if (
            !existingInfo ||
            !existingInfo.max_input_tokens ||
            existingInfo.input_cost_per_million === undefined ||
            existingInfo.output_cost_per_million === undefined
          ) {
            toast({
              title: t('modelInfo.missingInfo'),
              description: t('modelInfo.pleaseEditModelInfo'),
              variant: 'default',
            });
          }
        }
      } finally {
        setLoadingModels((prev) => {
          const next = new Set(prev);
          next.delete(model);
          return next;
        });
      }
    }
  };

  return {
    loadingModels,
    modelStatus,
    infoDialogModel,
    setInfoDialogModel,
    importDialogOpen,
    setImportDialogOpen,
    handleGetModels,
    handleImportModels,
    handleToggleModel,
  };
};

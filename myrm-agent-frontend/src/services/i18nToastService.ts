/**
 * 国际化 Toast 服务
 * 提供在 store 等非 React 组件中使用带翻译的 toast 的能力
 * 使用兼容包装器实现
 */

import { toast } from '@/lib/utils/toast';
import type { ExternalToast } from 'sonner';

/** 翻译参数值类型（与 next-intl 兼容） */
type TranslationValues = Record<string, string | number | boolean | Date | null | undefined>;

/**
 * 翻译函数类型
 * 使用更宽松的参数类型以兼容 next-intl 的 Translator 类型
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TranslatorFunction = (key: string, values?: Record<string, any>) => string;

// 全局翻译函数引用
let globalTranslator: TranslatorFunction | null = null;

/**
 * 设置全局翻译函数
 * 应该在应用初始化时调用
 */
export const setGlobalTranslator = (translator: TranslatorFunction) => {
  globalTranslator = translator;
};

/**
 * 使用翻译 key 显示 toast
 */
export const showI18nToast = (
  titleKey: string,
  values?: TranslationValues,
  options?: {
    description?: string;
    descriptionKey?: string;
    descriptionValues?: TranslationValues;
    duration?: number;
    type?: 'default' | 'error' | 'success' | 'warning' | 'info';
    action?: { label: string; onClick: () => void };
  },
) => {
  if (!globalTranslator) {
    console.warn('Global translator not initialized. Call setGlobalTranslator first.');
    toast(titleKey, {
      description: options?.description || options?.descriptionKey,
      duration: options?.duration || 3000,
    });
    return;
  }

  const title = globalTranslator(titleKey, values);

  let description = options?.description;
  if (options?.descriptionKey) {
    description = globalTranslator(options.descriptionKey, options.descriptionValues);
  }

  const sonnerOptions: ExternalToast = {
    description,
    duration: options?.duration || 3000,
  };

  if (options?.action) {
    sonnerOptions.action = {
      label: globalTranslator(options.action.label),
      onClick: options.action.onClick,
    };
  }

  const type = options?.type || 'default';

  switch (type) {
    case 'error':
      toast.error(title, sonnerOptions);
      break;
    case 'success':
      toast.success(title, sonnerOptions);
      break;
    case 'warning':
      toast.warning(title, sonnerOptions);
      break;
    case 'info':
      toast.info(title, sonnerOptions);
      break;
    default:
      toast(title, sonnerOptions);
  }
};

/**
 * 显示视觉模型切换提示
 */
export const showVisionModelSwitchedToast = (modelName: string) => {
  showI18nToast('chat.visionModelSwitched', { modelName });
};

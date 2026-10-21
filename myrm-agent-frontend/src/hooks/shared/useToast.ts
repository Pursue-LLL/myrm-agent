'use client';

/**
 * Toast Hook - 使用兼容包装器
 * 支持 shadcn/ui 和 Sonner 两种 API 格式
 */

import { toast } from '@/lib/utils/toast';

// 导出兼容包装器
export { toast };
export type { ExternalToast, ToastT } from 'sonner';
export type { ToastOptions } from '@/lib/utils/toast';

/**
 * useToast Hook - 返回兼容的 toast API
 */
export function useToast() {
  return {
    toast,
    success: toast.success,
    error: toast.error,
    warning: toast.warning,
    info: toast.info,
    dismiss: toast.dismiss,
  };
}

/**
 * Toast 包装器 - 兼容 shadcn/ui 和 Sonner API
 * 统一 toast 调用方式，避免 API 不兼容导致的运行时错误
 */

import { toast as sonnerToast, ExternalToast } from 'sonner';

/** Toast 选项（兼容 shadcn/ui toast） */
interface ToastOptions extends ExternalToast {
  title?: string;
  variant?: 'default' | 'destructive';
}

/** Toast 函数重载签名 */
interface ToastFunction {
  // Sonner 原生格式：toast(message, options)
  (message: string | React.ReactNode, options?: ExternalToast): string | number;
  // shadcn/ui 格式：toast({ title, description, variant })
  (options: ToastOptions): string | number;
  // 各种类型方法
  success: typeof sonnerToast.success;
  error: typeof sonnerToast.error;
  warning: typeof sonnerToast.warning;
  info: typeof sonnerToast.info;
  promise: typeof sonnerToast.promise;
  loading: typeof sonnerToast.loading;
  dismiss: typeof sonnerToast.dismiss;
  message: typeof sonnerToast.message;
}

/**
 * 统一的 toast 函数
 * 自动检测调用格式并转换为 Sonner API
 */
const toast: ToastFunction = ((
  messageOrOptions: string | React.ReactNode | ToastOptions,
  maybeOptions?: ExternalToast,
) => {
  // 如果第一个参数是对象且包含 title 字段，认为是 shadcn/ui 格式
  if (
    typeof messageOrOptions === 'object' &&
    messageOrOptions !== null &&
    'title' in messageOrOptions &&
    typeof messageOrOptions.title === 'string'
  ) {
    const { title, variant, ...restOptions } = messageOrOptions as ToastOptions;

    // 根据 variant 决定使用哪种 toast 类型
    if (variant === 'destructive') {
      return sonnerToast.error(title, restOptions);
    }

    return sonnerToast(title, restOptions);
  }

  // 否则认为是 Sonner 原生格式：toast(message, options)
  return sonnerToast(messageOrOptions as string | React.ReactNode, maybeOptions);
}) as ToastFunction;

// 绑定所有 Sonner 的方法到 toast 对象上
toast.success = sonnerToast.success.bind(sonnerToast);
toast.error = sonnerToast.error.bind(sonnerToast);
toast.warning = sonnerToast.warning.bind(sonnerToast);
toast.info = sonnerToast.info.bind(sonnerToast);
toast.promise = sonnerToast.promise.bind(sonnerToast);
toast.loading = sonnerToast.loading.bind(sonnerToast);
toast.dismiss = sonnerToast.dismiss.bind(sonnerToast);
toast.message = sonnerToast.message.bind(sonnerToast);

export { toast };
export type { ToastOptions, ToastFunction };

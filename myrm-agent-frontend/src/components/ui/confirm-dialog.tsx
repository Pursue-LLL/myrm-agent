'use client';

import { ReactNode, useState } from 'react';
import { Trash2, AlertTriangle, Info } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils/classnameUtils';

type ConfirmDialogVariant = 'destructive' | 'warning' | 'info';

interface ConfirmDialogProps {
  // 触发器
  trigger?: ReactNode;

  // 对话框内容
  title: string;
  description: string;

  // 按钮文本
  confirmText: string;
  cancelText: string;
  loadingText?: string;

  // 样式变体
  variant?: ConfirmDialogVariant;

  // 回调函数
  onConfirm: () => Promise<void> | void;
  onCancel?: () => void;

  // 受控模式
  open?: boolean;
  onOpenChange?: (open: boolean) => void;

  // 自定义图标
  icon?: ReactNode;

  // 自定义样式
  className?: string;
}

const variantConfig: Record<
  ConfirmDialogVariant,
  {
    icon: typeof Trash2;
    iconColor: string;
    buttonClass: string;
  }
> = {
  destructive: {
    icon: Trash2,
    iconColor: 'text-destructive',
    buttonClass: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
  },
  warning: {
    icon: AlertTriangle,
    iconColor: 'text-amber-500',
    buttonClass: 'bg-amber-500 text-white hover:bg-amber-600',
  },
  info: {
    icon: Info,
    iconColor: 'text-blue-500',
    buttonClass: 'bg-primary text-primary-foreground hover:bg-primary/90',
  },
};

/**
 * 通用确认对话框组件
 *
 * @example
 * ```tsx
 * <ConfirmDialog
 *   trigger={<button>Delete</button>}
 *   title="Delete Item"
 *   description="Are you sure you want to delete this item?"
 *   confirmText="Delete"
 *   cancelText="Cancel"
 *   variant="destructive"
 *   onConfirm={async () => await deleteItem()}
 * />
 * ```
 */
export const ConfirmDialog = ({
  trigger,
  title,
  description,
  confirmText,
  cancelText,
  loadingText,
  variant = 'destructive',
  onConfirm,
  onCancel,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  icon,
  className,
}: ConfirmDialogProps) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // 使用受控或非受控模式
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen;
  const setOpen = (value: boolean) => {
    if (controlledOnOpenChange) {
      controlledOnOpenChange(value);
    } else {
      setInternalOpen(value);
    }
  };

  const config = variantConfig[variant];
  const Icon = icon || <config.icon size={20} />;

  const handleConfirm = async (e: React.MouseEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await onConfirm();
      setOpen(false);
    } catch (error) {
      console.error('Confirm action failed:', error);
      // 不自动关闭对话框，让用户看到错误
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = () => {
    onCancel?.();
    setOpen(false);
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      {trigger && <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>}
      <AlertDialogContent className={cn('sm:max-w-[425px]', 'animate-in fade-in-0 zoom-in-95 duration-200', className)}>
        <AlertDialogHeader>
          <AlertDialogTitle
            className={cn('flex items-center gap-2 animate-in slide-in-from-top-2 duration-300', config.iconColor)}
          >
            {Icon}
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base pt-2 animate-in slide-in-from-top-4 duration-300 delay-75 whitespace-pre-line">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="sm:space-x-2 animate-in slide-in-from-bottom-2 duration-300 delay-100">
          <AlertDialogCancel
            disabled={isLoading}
            onClick={handleCancel}
            className="transition-all duration-200 hover:scale-105"
          >
            {cancelText}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isLoading}
            className={cn(
              config.buttonClass,
              'transition-all duration-200 hover:scale-105 hover:shadow-md',
              isLoading && 'opacity-70 cursor-wait',
            )}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg
                  className="animate-spin h-4 w-4"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                {loadingText || confirmText}
              </span>
            ) : (
              confirmText
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

/**
 * 删除确认对话框的快捷组件
 */
export const DeleteConfirmDialog = ({
  trigger,
  itemName,
  onConfirm,
  ...props
}: Omit<ConfirmDialogProps, 'title' | 'description' | 'variant'> & {
  itemName?: string;
}) => {
  return (
    <ConfirmDialog
      trigger={trigger}
      title={props.confirmText}
      description={
        itemName
          ? `Are you sure you want to delete ${itemName}? This action cannot be undone.`
          : 'This action cannot be undone.'
      }
      variant="destructive"
      onConfirm={onConfirm}
      {...props}
    />
  );
};

export default ConfirmDialog;

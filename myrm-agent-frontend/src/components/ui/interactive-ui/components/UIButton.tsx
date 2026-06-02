/**
 * UI 按钮组件
 * 支持 loading 状态和图标
 */

import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

export const UIButton: React.FC<UIComponentProps> = ({ props, events, onAction }) => {
  const label = (props.label as string) || 'Button';
  const variant = (props.variant as 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger') || 'primary';
  const disabled = (props.disabled as boolean) || false;
  const loading = (props.loading as boolean) || false;
  const size = (props.size as 'sm' | 'md' | 'lg') || 'md';
  const fullWidth = (props.fullWidth as boolean) || false;
  const className = (props.className as string) || '';

  const handleClick = () => {
    if (loading) return; // 加载中不允许点击
    const actionId = events.onClick;
    if (actionId) {
      onAction(actionId);
    }
  };

  const baseClasses =
    'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2';

  const variantClasses: Record<string, string> = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500 disabled:bg-blue-400',
    secondary:
      'bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-500 dark:bg-gray-700 dark:text-gray-100 dark:hover:bg-gray-600',
    outline:
      'border-2 border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800',
    ghost: 'text-gray-700 hover:bg-gray-100 focus:ring-gray-500 dark:text-gray-300 dark:hover:bg-gray-800',
    danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 disabled:bg-red-400',
  };

  const sizeClasses: Record<string, string> = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  };

  const isDisabled = disabled || loading;

  return (
    <button
      type="button"
      disabled={isDisabled}
      onClick={handleClick}
      className={cn(
        baseClasses,
        variantClasses[variant] || variantClasses.primary,
        sizeClasses[size],
        isDisabled && 'cursor-not-allowed opacity-50',
        fullWidth && 'w-full',
        className,
      )}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {label}
    </button>
  );
};

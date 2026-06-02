/**
 * UI 卡片容器组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

export const UICard: React.FC<UIComponentProps> = ({ props, children, className }) => {
  const title = (props.title as string) || '';
  const description = (props.description as string) || '';
  const variant = (props.variant as 'default' | 'outlined' | 'elevated') || 'default';

  const variantClasses: Record<string, string> = {
    default: 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700',
    outlined: 'border-2 border-gray-300 dark:border-gray-600 bg-transparent',
    elevated: 'bg-white dark:bg-gray-800 shadow-lg border-0',
  };

  return (
    <div className={cn('rounded-xl p-4', variantClasses[variant], className)}>
      {title && (
        <div className="mb-3">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
          {description && <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
      )}
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  );
};

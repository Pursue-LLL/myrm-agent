/**
 * UI 进度条组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

export const UIProgress: React.FC<UIComponentProps> = ({ props, bindings, data }) => {
  const label = (props.label as string) || '';
  const max = (props.max as number) || 100;
  const showValue = (props.showValue as boolean) ?? true;
  const size = (props.size as 'sm' | 'md' | 'lg') || 'md';
  const color = (props.color as 'blue' | 'green' | 'yellow' | 'red') || 'blue';
  const className = (props.className as string) || '';

  const valuePath = bindings.value;
  const value = valuePath ? (getValueByPath(data, valuePath) as number) || 0 : (props.value as number) || 0;
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  const sizeClasses: Record<string, string> = {
    sm: 'h-1.5',
    md: 'h-2.5',
    lg: 'h-4',
  };

  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-600',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  };

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between">
          {label && <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>}
          {showValue && (
            <span className="text-sm text-gray-500 dark:text-gray-400 tabular-nums">{Math.round(percentage)}%</span>
          )}
        </div>
      )}
      <div className={cn('w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden', sizeClasses[size])}>
        <div
          className={cn('h-full rounded-full transition-all duration-300', colorClasses[color])}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

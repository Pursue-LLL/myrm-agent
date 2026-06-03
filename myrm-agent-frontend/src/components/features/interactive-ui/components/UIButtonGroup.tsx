/**
 * UI 按钮组组件（单选/多选）
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

type ButtonOption = string | { value: string; label: string };

export const UIButtonGroup: React.FC<UIComponentProps> = ({ props, bindings, data, onDataChange }) => {
  const label = (props.label as string) || '';
  const options = (props.options as ButtonOption[]) || [];
  const multiple = (props.multiple as boolean) || false;
  const disabled = (props.disabled as boolean) || false;
  const size = (props.size as 'sm' | 'md' | 'lg') || 'md';
  const className = (props.className as string) || '';

  const valuePath = bindings.value;
  const rawValue = valuePath ? getValueByPath(data, valuePath) : null;

  const selectedValues: string[] = multiple
    ? Array.isArray(rawValue)
      ? (rawValue as string[])
      : []
    : rawValue
      ? [String(rawValue)]
      : [];

  // 标准化选项格式
  const normalizedOptions = options.map((opt) => (typeof opt === 'string' ? { value: opt, label: opt } : opt));

  const handleSelect = (optionValue: string) => {
    if (disabled || !valuePath) return;

    if (multiple) {
      const newValues = selectedValues.includes(optionValue)
        ? selectedValues.filter((v) => v !== optionValue)
        : [...selectedValues, optionValue];
      onDataChange(valuePath, newValues);
    } else {
      onDataChange(valuePath, optionValue);
    }
  };

  const sizeClasses: Record<string, string> = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-1.5 text-sm',
    lg: 'px-4 py-2 text-base',
  };

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {label && <label className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>}
      <div className="flex flex-wrap gap-2">
        {normalizedOptions.map((opt) => {
          const isSelected = selectedValues.includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              disabled={disabled}
              onClick={() => handleSelect(opt.value)}
              className={cn(
                'rounded-lg font-medium transition-all duration-200',
                'border-2 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500',
                sizeClasses[size],
                isSelected
                  ? 'border-blue-600 bg-blue-600 text-white'
                  : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800',
                disabled && 'opacity-50 cursor-not-allowed',
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};

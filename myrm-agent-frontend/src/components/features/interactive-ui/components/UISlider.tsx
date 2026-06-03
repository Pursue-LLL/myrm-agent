/**
 * UI 滑块组件
 * 支持验证规则和错误显示
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

export const UISlider: React.FC<UIComponentProps> = ({
  props,
  bindings,
  data,
  onDataChange,
  validationError,
  onBlur,
}) => {
  const label = (props.label as string) || '';
  const min = (props.min as number) || 0;
  const max = (props.max as number) || 100;
  const step = (props.step as number) || 1;
  const disabled = (props.disabled as boolean) || false;
  const showValue = (props.showValue as boolean) ?? true;
  const required = (props.required as boolean) || false;
  const className = (props.className as string) || '';

  const valuePath = bindings.value;
  const value = valuePath ? (getValueByPath(data, valuePath) as number) || min : min;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (valuePath) {
      onDataChange(valuePath, Number(e.target.value));
    }
  };

  const handleBlur = () => {
    if (valuePath && onBlur) {
      onBlur(valuePath);
    }
  };

  const hasError = !!validationError;

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {label && (
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
            {required && <span className="text-red-500 ml-1">*</span>}
          </label>
          {showValue && (
            <span
              className={cn(
                'text-sm tabular-nums',
                hasError ? 'text-red-500 dark:text-red-400' : 'text-gray-500 dark:text-gray-400',
              )}
            >
              {value}
            </span>
          )}
        </div>
      )}
      <input
        type="range"
        value={value}
        onChange={handleChange}
        onBlur={handleBlur}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        className={cn(
          'w-full h-2 rounded-lg appearance-none cursor-pointer',
          'bg-gray-200 dark:bg-gray-700',
          hasError ? 'accent-red-500' : 'accent-blue-600',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
      />
      {/* 验证错误消息 */}
      {hasError && (
        <p className="text-xs text-red-500 dark:text-red-400 flex items-center gap-1 animate-in fade-in-0 slide-in-from-top-1 duration-200">
          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          {validationError}
        </p>
      )}
    </div>
  );
};

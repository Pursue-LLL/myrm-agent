/**
 * UI 复选框组件
 * 支持验证规则和错误显示
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

export const UICheckbox: React.FC<UIComponentProps> = ({
  props,
  bindings,
  data,
  onDataChange,
  validationError,
  onBlur,
}) => {
  const label = (props.label as string) || '';
  const disabled = (props.disabled as boolean) || false;
  const required = (props.required as boolean) || false;
  const className = (props.className as string) || '';

  const valuePath = bindings.value;
  const checked = valuePath ? (getValueByPath(data, valuePath) as boolean) || false : false;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (valuePath) {
      onDataChange(valuePath, e.target.checked);
    }
  };

  const handleBlur = () => {
    if (valuePath && onBlur) {
      onBlur(valuePath);
    }
  };

  const hasError = !!validationError;

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label className={cn('flex items-center gap-2 cursor-pointer', disabled && 'opacity-50 cursor-not-allowed')}>
        <input
          type="checkbox"
          checked={checked}
          onChange={handleChange}
          onBlur={handleBlur}
          disabled={disabled}
          className={cn(
            'w-4 h-4 rounded border transition-colors duration-200',
            !hasError && 'text-blue-600 border-gray-300 dark:border-gray-600',
            hasError && 'text-red-500 border-red-400 dark:border-red-500',
            'focus:ring-2 focus:ring-offset-0',
            !hasError && 'focus:ring-blue-500',
            hasError && 'focus:ring-red-500',
          )}
        />
        {label && (
          <span
            className={cn('text-sm', hasError ? 'text-red-600 dark:text-red-400' : 'text-gray-700 dark:text-gray-300')}
          >
            {label}
            {required && <span className="text-red-500 ml-1">*</span>}
          </span>
        )}
      </label>
      {/* 验证错误消息 */}
      {hasError && (
        <p className="text-xs text-red-500 dark:text-red-400 flex items-center gap-1 ml-6 animate-in fade-in-0 slide-in-from-top-1 duration-200">
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

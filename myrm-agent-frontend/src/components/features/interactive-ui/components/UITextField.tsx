/**
 * UI 文本输入框组件
 * 支持验证规则和错误显示
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

export const UITextField: React.FC<UIComponentProps> = ({
  props,
  bindings,
  data,
  onDataChange,
  validationError,
  onBlur,
}) => {
  const label = (props.label as string) || '';
  const placeholder = (props.placeholder as string) || '';
  const disabled = (props.disabled as boolean) || false;
  const required = (props.required as boolean) || false;
  const type = (props.type as 'text' | 'email' | 'password' | 'number') || 'text';
  const className = (props.className as string) || '';

  // 从数据模型获取值
  const valuePath = bindings.value;
  const value = valuePath ? (getValueByPath(data, valuePath) as string) || '' : '';

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (valuePath) {
      onDataChange(valuePath, e.target.value);
    }
  };

  const handleBlur = () => {
    if (valuePath && onBlur) {
      onBlur(valuePath);
    }
  };

  const hasError = !!validationError;

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {label && (
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={handleChange}
        onBlur={handleBlur}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        className={cn(
          'w-full px-3 py-2 rounded-lg border transition-all duration-200',
          'bg-white dark:bg-gray-800',
          'text-gray-900 dark:text-gray-100',
          'placeholder-gray-400 dark:placeholder-gray-500',
          'focus:outline-none focus:ring-2 focus:border-transparent',
          // 正常状态
          !hasError && 'border-gray-300 dark:border-gray-600 focus:ring-blue-500',
          // 错误状态
          hasError && 'border-red-400 dark:border-red-500 focus:ring-red-500 bg-red-50/50 dark:bg-red-900/10',
          disabled && 'opacity-50 cursor-not-allowed bg-gray-100 dark:bg-gray-900',
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

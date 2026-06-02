/**
 * UI 开关组件
 * 支持验证规则和错误显示
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

export const UISwitch: React.FC<UIComponentProps> = ({
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

  const handleToggle = () => {
    if (!disabled && valuePath) {
      onDataChange(valuePath, !checked);
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
      <div className={cn('flex items-center gap-3', disabled && 'opacity-50 cursor-not-allowed')}>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={disabled}
          onClick={handleToggle}
          onBlur={handleBlur}
          className={cn(
            'relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent',
            'transition-colors duration-200 ease-in-out',
            'focus:outline-none focus:ring-2 focus:ring-offset-2',
            !hasError && (checked ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'),
            !hasError && 'focus:ring-blue-500',
            hasError && (checked ? 'bg-red-500' : 'bg-red-200 dark:bg-red-800'),
            hasError && 'focus:ring-red-500',
            !disabled && 'cursor-pointer',
          )}
        >
          <span
            className={cn(
              'pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg',
              'ring-0 transition duration-200 ease-in-out',
              checked ? 'translate-x-5' : 'translate-x-0',
            )}
          />
        </button>
        {label && (
          <span
            className={cn('text-sm', hasError ? 'text-red-600 dark:text-red-400' : 'text-gray-700 dark:text-gray-300')}
          >
            {label}
            {required && <span className="text-red-500 ml-1">*</span>}
          </span>
        )}
      </div>
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

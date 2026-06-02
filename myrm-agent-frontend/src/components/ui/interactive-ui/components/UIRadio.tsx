/**
 * UI 单选按钮组组件
 * 支持验证规则和错误显示
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

type RadioOption = string | { value: string; label: string; disabled?: boolean };

export const UIRadio: React.FC<UIComponentProps> = ({
  id,
  props,
  bindings,
  data,
  onDataChange,
  validationError,
  onBlur,
}) => {
  const label = (props.label as string) || '';
  const options = (props.options as RadioOption[]) || [];
  const disabled = (props.disabled as boolean) || false;
  const required = (props.required as boolean) || false;
  const className = (props.className as string) || '';
  const layout = (props.layout as 'horizontal' | 'vertical') || 'vertical';

  const valuePath = bindings.value;
  const value = valuePath ? (getValueByPath(data, valuePath) as string) || '' : '';

  const handleChange = (newValue: string) => {
    if (valuePath && !disabled) {
      onDataChange(valuePath, newValue);
    }
  };

  const handleBlur = () => {
    if (valuePath && onBlur) {
      onBlur(valuePath);
    }
  };

  const hasError = !!validationError;

  // 标准化选项格式
  const normalizedOptions = options.map((opt) =>
    typeof opt === 'string' ? { value: opt, label: opt, disabled: false } : opt,
  );

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {label && (
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      <div
        className={cn('flex gap-3', layout === 'vertical' ? 'flex-col' : 'flex-row flex-wrap')}
        role="radiogroup"
        aria-label={label}
        onBlur={handleBlur}
      >
        {normalizedOptions.map((option, _index) => {
          const isSelected = value === option.value;
          const isDisabled = disabled || option.disabled;

          return (
            <label
              key={option.value}
              className={cn(
                'flex items-center gap-2 cursor-pointer group',
                isDisabled && 'opacity-50 cursor-not-allowed',
              )}
            >
              <div className="relative">
                <input
                  type="radio"
                  name={`radio-${id}`}
                  value={option.value}
                  checked={isSelected}
                  onChange={() => handleChange(option.value)}
                  disabled={isDisabled}
                  className="sr-only"
                />
                <div
                  className={cn(
                    'w-4 h-4 rounded-full border-2 transition-all duration-200',
                    'flex items-center justify-center',
                    // 正常状态
                    !isSelected && !hasError && 'border-gray-300 dark:border-gray-600 group-hover:border-blue-400',
                    // 选中状态
                    isSelected && !hasError && 'border-blue-500 bg-blue-500',
                    // 错误状态
                    hasError && !isSelected && 'border-red-400 dark:border-red-500',
                    hasError && isSelected && 'border-red-500 bg-red-500',
                  )}
                >
                  {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                </div>
              </div>
              <span
                className={cn(
                  'text-sm',
                  isDisabled ? 'text-gray-400 dark:text-gray-500' : 'text-gray-700 dark:text-gray-300',
                )}
              >
                {option.label}
              </span>
            </label>
          );
        })}
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

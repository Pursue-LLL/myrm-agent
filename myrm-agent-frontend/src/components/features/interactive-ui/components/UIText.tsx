/**
 * UI 文本组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

export const UIText: React.FC<UIComponentProps> = ({ props }) => {
  const text = (props.text as string) || '';
  const variant = (props.variant as 'body' | 'heading' | 'caption' | 'label') || 'body';
  const className = (props.className as string) || '';

  const variantClasses: Record<string, string> = {
    body: 'text-sm text-gray-700 dark:text-gray-300',
    heading: 'text-lg font-semibold text-gray-900 dark:text-gray-100',
    caption: 'text-xs text-gray-500 dark:text-gray-400',
    label: 'text-sm font-medium text-gray-700 dark:text-gray-300',
  };

  return <span className={cn(variantClasses[variant], className)}>{text}</span>;
};

/**
 * UI 分隔线组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

export const UIDivider: React.FC<UIComponentProps> = ({ props }) => {
  const orientation = (props.orientation as 'horizontal' | 'vertical') || 'horizontal';
  const className = (props.className as string) || '';

  return (
    <hr
      className={cn(
        'border-gray-200 dark:border-gray-700',
        orientation === 'vertical' ? 'border-l h-full w-0' : 'border-t w-full h-0',
        className,
      )}
    />
  );
};

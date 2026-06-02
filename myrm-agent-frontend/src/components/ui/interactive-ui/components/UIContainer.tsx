/**
 * UI 容器组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

export const UIContainer: React.FC<UIComponentProps> = ({ props, children }) => {
  const direction = (props.direction as 'row' | 'column') || 'column';
  const gap = (props.gap as 'none' | 'sm' | 'md' | 'lg') || 'md';
  const align = (props.align as 'start' | 'center' | 'end' | 'stretch') || 'stretch';
  const justify = (props.justify as 'start' | 'center' | 'end' | 'between' | 'around') || 'start';
  const wrap = (props.wrap as boolean) || false;
  const className = (props.className as string) || '';

  const gapClasses: Record<string, string> = {
    none: 'gap-0',
    sm: 'gap-2',
    md: 'gap-4',
    lg: 'gap-6',
  };

  const alignClasses: Record<string, string> = {
    start: 'items-start',
    center: 'items-center',
    end: 'items-end',
    stretch: 'items-stretch',
  };

  const justifyClasses: Record<string, string> = {
    start: 'justify-start',
    center: 'justify-center',
    end: 'justify-end',
    between: 'justify-between',
    around: 'justify-around',
  };

  return (
    <div
      className={cn(
        'flex',
        direction === 'row' ? 'flex-row' : 'flex-col',
        gapClasses[gap],
        alignClasses[align],
        justifyClasses[justify],
        wrap && 'flex-wrap',
        className,
      )}
    >
      {children}
    </div>
  );
};

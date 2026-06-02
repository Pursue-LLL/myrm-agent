/**
 * UI Grid 布局组件
 * 支持灵活的网格布局
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

export const UIGrid: React.FC<UIComponentProps> = ({ props, children }) => {
  const columns = (props.columns as number) || 2;
  const gap = (props.gap as number) || 4;
  const className = (props.className as string) || '';
  const alignItems = (props.alignItems as string | undefined) || 'stretch';

  // 响应式列数配置
  const mobileColumns = (props.mobileColumns as number) || 1;
  const tabletColumns = (props.tabletColumns as number) || Math.min(columns, 2);

  // 对齐方式
  // 使用 CSS Grid 模板列
  const getColumnsClass = () => {
    // 响应式处理
    const colClasses: string[] = [];

    // 移动端
    if (mobileColumns === 1) colClasses.push('grid-cols-1');
    else if (mobileColumns === 2) colClasses.push('grid-cols-2');
    else colClasses.push(`grid-cols-${mobileColumns}`);

    // 平板
    if (tabletColumns === 1) colClasses.push('md:grid-cols-1');
    else if (tabletColumns === 2) colClasses.push('md:grid-cols-2');
    else if (tabletColumns === 3) colClasses.push('md:grid-cols-3');
    else colClasses.push(`md:grid-cols-${tabletColumns}`);

    // 桌面
    if (columns === 1) colClasses.push('lg:grid-cols-1');
    else if (columns === 2) colClasses.push('lg:grid-cols-2');
    else if (columns === 3) colClasses.push('lg:grid-cols-3');
    else if (columns === 4) colClasses.push('lg:grid-cols-4');
    else if (columns === 5) colClasses.push('lg:grid-cols-5');
    else if (columns === 6) colClasses.push('lg:grid-cols-6');
    else colClasses.push(`lg:grid-cols-${columns}`);

    return colClasses.join(' ');
  };

  const getGapClass = () => {
    if (gap === 1) return 'gap-1';
    if (gap === 2) return 'gap-2';
    if (gap === 3) return 'gap-3';
    if (gap === 4) return 'gap-4';
    if (gap === 5) return 'gap-5';
    if (gap === 6) return 'gap-6';
    if (gap === 8) return 'gap-8';
    return `gap-${gap}`;
  };

  return (
    <div
      className={cn(
        'grid',
        getColumnsClass(),
        getGapClass(),
        {
          'items-start': alignItems === 'start',
          'items-center': alignItems === 'center',
          'items-end': alignItems === 'end',
          'items-stretch': alignItems === 'stretch',
        },
        className,
      )}
    >
      {children}
    </div>
  );
};

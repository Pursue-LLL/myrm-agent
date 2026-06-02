/**
 * UI 选项卡布局组件
 *
 * 基于 shadcn/radix Tabs，用于分类内容展示。
 * props.tabs 定义标签名，children 按序对应各 tab 的内容面板。
 */

import React from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';

interface TabDefinition {
  label: string;
}

export const UITabs: React.FC<UIComponentProps> = ({ props, children }) => {
  const tabs = (props.tabs as TabDefinition[]) || [];
  const defaultIndex = (props.defaultIndex as number) || 0;
  const variant = (props.variant as 'default' | 'outline') || 'default';

  const childArray = React.Children.toArray(children);

  if (tabs.length === 0) {
    return <>{children}</>;
  }

  return (
    <Tabs defaultValue={String(defaultIndex)} className="w-full">
      <TabsList
        className={cn(
          'overflow-x-auto scrollbar-hide',
          variant === 'outline' && 'bg-transparent border border-gray-200 dark:border-gray-700',
        )}
      >
        {tabs.map((tab, i) => (
          <TabsTrigger key={i} value={String(i)}>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((_, i) => (
        <TabsContent key={i} value={String(i)}>
          {childArray[i] ?? null}
        </TabsContent>
      ))}
    </Tabs>
  );
};

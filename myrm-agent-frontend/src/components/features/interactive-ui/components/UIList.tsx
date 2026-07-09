/**
 * UI 列表组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

interface ListItem {
  id?: string;
  title: string;
  subtitle?: string;
  description?: string;
}

function isListItem(value: unknown): value is ListItem {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const record = value as Record<string, unknown>;
  return typeof record.title === 'string';
}

export const UIList: React.FC<UIComponentProps> = ({ props, bindings, data, children }) => {
  const t = useTranslations('interactiveUI');
  const bordered = (props.bordered as boolean) ?? false;
  const compact = (props.compact as boolean) ?? false;
  const className = (props.className as string) || '';
  const emptyText = (props.emptyText as string) || t('noData');

  const dataPath = bindings.data;
  const rawData = dataPath ? getValueByPath(data, dataPath) : undefined;
  const items: ListItem[] = Array.isArray(rawData) ? rawData.filter(isListItem) : [];

  if (children) {
    return (
      <ul
        className={cn(
          'flex flex-col',
          compact ? 'gap-1' : 'gap-2',
          bordered && 'rounded-md border border-gray-200 dark:border-gray-700',
          className,
        )}
      >
        {children}
      </ul>
    );
  }

  if (items.length === 0) {
    return (
      <p className={cn('text-sm text-gray-500 dark:text-gray-400', className)}>
        {emptyText}
      </p>
    );
  }

  return (
    <ul
      className={cn(
        'flex flex-col',
        compact ? 'gap-1' : 'gap-2',
        bordered && 'rounded-md border border-gray-200 dark:border-gray-700',
        className,
      )}
    >
      {items.map((item, index) => (
        <li
          key={item.id ?? index}
          className={cn(
            'rounded-md bg-gray-50/80 dark:bg-gray-800/50',
            compact ? 'px-3 py-2' : 'px-4 py-3',
            bordered && 'border border-gray-200 dark:border-gray-700',
          )}
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">{item.title}</div>
          {item.subtitle && (
            <div className="text-sm text-gray-600 dark:text-gray-300">{item.subtitle}</div>
          )}
          {item.description && (
            <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">{item.description}</div>
          )}
        </li>
      ))}
    </ul>
  );
};

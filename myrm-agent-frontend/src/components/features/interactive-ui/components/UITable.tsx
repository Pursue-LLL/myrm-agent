/**
 * UI 表格组件
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

interface TableColumn {
  key: string;
  title: string;
  width?: string;
}

export const UITable: React.FC<UIComponentProps> = ({ props, bindings, data }) => {
  const t = useTranslations('interactiveUI');
  const columns = (props.columns as TableColumn[]) || [];
  const striped = (props.striped as boolean) ?? true;
  const bordered = (props.bordered as boolean) ?? false;
  const compact = (props.compact as boolean) ?? false;
  const className = (props.className as string) || '';

  const dataPath = bindings.data;
  const rawData = dataPath ? getValueByPath(data, dataPath) : undefined;
  const tableData = Array.isArray(rawData) ? (rawData as Record<string, unknown>[]) : [];

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className={cn('w-full text-sm', bordered && 'border border-gray-200 dark:border-gray-700')}>
        <thead>
          <tr className={cn('bg-gray-50 dark:bg-gray-800', 'border-b border-gray-200 dark:border-gray-700')}>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width }}
                className={cn(
                  'text-left font-medium text-gray-700 dark:text-gray-300',
                  compact ? 'px-3 py-2' : 'px-4 py-3',
                  bordered && 'border-r border-gray-200 dark:border-gray-700 last:border-r-0',
                )}
              >
                {col.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableData.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                {t('noData')}
              </td>
            </tr>
          ) : (
            tableData.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className={cn(
                  'border-b border-gray-200 dark:border-gray-700 last:border-b-0',
                  striped && rowIndex % 2 === 1 && 'bg-gray-50/50 dark:bg-gray-800/50',
                )}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      'text-gray-900 dark:text-gray-100',
                      compact ? 'px-3 py-2' : 'px-4 py-3',
                      bordered && 'border-r border-gray-200 dark:border-gray-700 last:border-r-0',
                    )}
                  >
                    {String(row[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};

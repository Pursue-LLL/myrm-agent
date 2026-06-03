import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';

interface QueryItemsRendererProps {
  items: { query: string }[];
  messageId: string;
  stepIndex: number;
}

const QueryItemsRenderer: React.FC<QueryItemsRendererProps> = ({ items, messageId, stepIndex }) => {
  return (
    <div className="flex flex-wrap gap-2 sm:gap-2.5">
      {items.map((item, itemIndex) => (
        <div
          key={`${messageId}-query-${stepIndex}-${itemIndex}`}
          className={cn(
            'text-[11px] sm:text-xs inline-flex items-center gap-1.5 sm:gap-2',
            'py-1 sm:py-1.5 px-2 sm:px-3 rounded-lg',
            'bg-gradient-to-r from-border-50 to-indigo-50 dark:from-gray-700 dark:to-gray-600 bg-secondary',
            'border border-destructive-200/60 dark:border-gray-600/60',
            'text-gray-500 dark:text-gray-200',
            'transition-all duration-300',
            'hover:shadow-md hover:border-gray-300/80 dark:hover:border-gray-500/80',
            'hover:from-destructive-100 hover:to-indigo-100 dark:hover:from-gray-600 dark:hover:to-gray-500',
            'hover:scale-[1.02]',
            'w-full sm:w-auto',
            'break-all',
          )}
          title={item.query}
        >
          <span className="font-medium">{item.query}</span>
        </div>
      ))}
    </div>
  );
};

export default QueryItemsRenderer;

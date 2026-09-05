import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { ShieldCheck, GraduationCap, TrendingUp, Cpu } from 'lucide-react';

interface QueryItemsRendererProps {
  items: { query: string }[];
  messageId: string;
  stepIndex: number;
}

/**
 * Detect structured domain vertical indicator for enhanced search observability.
 */
function getDomainBadge(query: string): { label: string; icon: React.ReactNode } | null {
  const upper = query.toUpperCase();
  if (upper.includes('CVE-') || upper.includes('"CVE-')) {
    return {
      label: 'Security CVE',
      icon: <ShieldCheck className="w-3 h-3 text-red-500 shrink-0" />,
    };
  }
  if (query.includes('10.') && (query.includes('/') || upper.includes('DOI'))) {
    return {
      label: 'Academic DOI',
      icon: <GraduationCap className="w-3 h-3 text-blue-500 shrink-0" />,
    };
  }
  if (/(?:STOCK|QUOTE|TICKER|股价|美股|港股|A股)/i.test(query)) {
    return {
      label: 'Finance Market',
      icon: <TrendingUp className="w-3 h-3 text-emerald-500 shrink-0" />,
    };
  }
  if (/\b(?:GITHUB|NPM|PYPI|CRATE|STACKOVERFLOW)\b/i.test(query)) {
    return {
      label: 'Code Package',
      icon: <Cpu className="w-3 h-3 text-violet-500 shrink-0" />,
    };
  }
  return null;
}

const QueryItemsRenderer: React.FC<QueryItemsRendererProps> = ({ items, messageId, stepIndex }) => {
  return (
    <div className="flex flex-wrap gap-2 sm:gap-2.5">
      {items.map((item, itemIndex) => {
        const badge = getDomainBadge(item.query);
        return (
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
            {badge && (
              <span
                data-testid="domain-intent-pill"
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20 shrink-0"
              >
                {badge.icon}
                <span>{badge.label}</span>
              </span>
            )}
            <span className="font-medium">{item.query}</span>
          </div>
        );
      })}
    </div>
  );
};

export default QueryItemsRenderer;

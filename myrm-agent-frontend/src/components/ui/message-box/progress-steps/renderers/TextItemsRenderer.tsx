/* eslint-disable @next/next/no-img-element */
import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { isUrl, extractDomainFromUrl, isWebpageUrl } from '@/lib/utils/urlUtils';
import { EnhancedSyntaxHighlighter } from './EnhancedSyntaxHighlighter';

interface TextItemsRendererProps {
  items: { text: string }[];
  messageId: string;
  stepIndex: number;
  handleLinkClick: (text: string) => void;
}

const isJsonString = (str: string): { isJson: boolean; formatted: string; language: string } => {
  if (str.length < 20) return { isJson: false, formatted: str, language: 'text' };

  // 【性能探针熔断机制】超过 50KB 的字符串直接拒绝 JSON.parse 嗅探，防止主线程卡死
  if (str.length > 50000) {
    return { isJson: true, formatted: str, language: 'text' }; // 视为纯长文本渲染
  }

  const trimmed = str.trim();
  // Quick heuristic before JSON.parse
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      const parsed = JSON.parse(trimmed);
      return {
        isJson: true,
        formatted: JSON.stringify(parsed, null, 2),
        language: 'json',
      };
    } catch {
      return { isJson: false, formatted: str, language: 'text' };
    }
  }

  // Could it be a python dict string that is easily formatable? Or long code?
  // If it's very long and contains newlines, we can also treat it as text/code
  if (trimmed.length > 200 && trimmed.includes('\n')) {
    return { isJson: true, formatted: trimmed, language: 'text' };
  }

  return { isJson: false, formatted: str, language: 'text' };
};

const TextItemsRenderer: React.FC<TextItemsRendererProps> = ({ items, messageId, stepIndex, handleLinkClick }) => {
  // Check if we should render the entire items array as one big code block (if there's only one large text item)
  if (items.length === 1) {
    const { isJson, formatted, language } = isJsonString(items[0].text);
    if (isJson) {
      return <EnhancedSyntaxHighlighter code={formatted} language={language} />;
    }
  }

  return (
    <div className="flex flex-wrap gap-2 sm:gap-2.5 mt-2">
      {items.map((item, itemIndex) => {
        const { isJson, formatted, language } = isJsonString(item.text);

        // Render as enhanced code block if it is JSON
        if (isJson) {
          return (
            <div key={`${messageId}-item-${stepIndex}-${itemIndex}`} className="w-full">
              <EnhancedSyntaxHighlighter code={formatted} language={language} />
            </div>
          );
        }

        const isLink = isUrl(item.text);
        let displayText = item.text;
        if (isLink) {
          try {
            displayText = extractDomainFromUrl(item.text);
          } catch (error) {
            console.warn('Failed to extract domain from URL:', item.text, error);
            displayText = item.text;
          }
        }
        const isWeb = isLink && isWebpageUrl(item.text);

        return (
          <div
            key={`${messageId}-item-${stepIndex}-${itemIndex}`}
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
              isLink && 'cursor-pointer hover:text-indigo-600 dark:hover:text-indigo-400',
            )}
            onClick={isLink ? () => handleLinkClick(item.text) : undefined}
            title={isLink ? item.text : ''}
          >
            {isWeb && (
              <div className="w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 rounded-lg overflow-hidden bg-white">
                <img
                  src={`https://s2.googleusercontent.com/s2/favicons?domain_url=${item.text}`}
                  width={16}
                  height={16}
                  alt="favicon"
                  className="object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              </div>
            )}
            <span className="font-medium whitespace-pre-wrap break-word" title={displayText}>
              {displayText}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export default TextItemsRenderer;

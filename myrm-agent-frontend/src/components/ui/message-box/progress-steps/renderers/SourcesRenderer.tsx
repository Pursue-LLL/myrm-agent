/* eslint-disable @next/next/no-img-element */
import React, { useState, useEffect } from 'react';
import { Globe } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { SourceItem } from '../utils';

interface SourcesRendererProps {
  items: SourceItem[];
  messageId: string;
  stepIndex: number;
  isCurrentStep: boolean;
}

const SourcesRenderer: React.FC<SourcesRendererProps> = ({ items, messageId, stepIndex, isCurrentStep }) => {
  const [visibleCount, setVisibleCount] = useState(isCurrentStep ? 0 : items.length);

  useEffect(() => {
    if (isCurrentStep && visibleCount < items.length) {
      const timer = setTimeout(() => {
        setVisibleCount((prev) => prev + 1);
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [visibleCount, items.length, isCurrentStep]);

  useEffect(() => {
    if (!isCurrentStep) {
      setVisibleCount(items.length);
    }
  }, [isCurrentStep, items.length]);

  const handleClick = (url?: string) => {
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className={cn('flex gap-2 mt-3 overflow-x-auto pb-2', 'custom-scrollbar')}>
      {items.slice(0, visibleCount).map((item, index) => {
        const domain = item.url
          ? (() => {
              try {
                return new URL(item.url).hostname.replace(/^www\./, '');
              } catch {
                return '';
              }
            })()
          : '';

        const faviconUrl = domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=64` : '';

        return (
          <div
            key={`${messageId}-source-${stepIndex}-${index}`}
            className={cn(
              'group flex-shrink-0 flex items-start gap-2 py-2 px-3 rounded-lg',
              'w-52 sm:w-60',
              'bg-gradient-to-r from-background to-primary/5',
              'border border-border/40 hover:border-primary/40',
              'cursor-pointer transition-all duration-200',
              'hover:bg-primary/5',
              'animate-in fade-in slide-in-from-right-2',
            )}
            style={{
              animationDelay: `${index * 50}ms`,
              animationDuration: '300ms',
            }}
            onClick={() => handleClick(item.url)}
            title={item.url}
          >
            {/* Favicon */}
            <div className="flex-shrink-0 w-6 h-6 rounded overflow-hidden bg-white/80 border border-border/20 mt-0.5">
              {faviconUrl ? (
                <img
                  src={faviconUrl}
                  width={24}
                  height={24}
                  alt="favicon"
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    const img = e.target as HTMLImageElement;
                    img.style.display = 'none';
                    const parent = img.parentElement;
                    if (parent) {
                      parent.innerHTML =
                        '<div class="w-full h-full flex items-center justify-center"><svg class="w-3 h-3 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg></div>';
                    }
                  }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <Globe className="w-3 h-3 text-muted-foreground" />
                </div>
              )}
            </div>

            {/* 内容 */}
            <div className="flex-1 min-w-0">
              {/* 标题（支持两行） */}
              <p
                className={cn(
                  'text-xs font-medium line-clamp-2 leading-relaxed',
                  'text-foreground/90 group-hover:text-primary',
                  'transition-colors duration-200',
                )}
              >
                {item.title || domain || 'Untitled'}
              </p>

              {/* 域名 */}
              {domain && <p className="text-[10px] text-muted-foreground truncate mt-1">{domain}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default SourcesRenderer;

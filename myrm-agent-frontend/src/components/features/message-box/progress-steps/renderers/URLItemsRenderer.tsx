/* eslint-disable @next/next/no-img-element */
import React, { useState, useEffect } from 'react';
import { Globe } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { isWebpageUrl } from '@/lib/utils/urlUtils';
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/primitives/carousel';

interface URLItemsRendererProps {
  items: { url: string }[];
  messageId: string;
  stepIndex: number;
  isCurrentStep: boolean;
  handleLinkClick: (url: string) => void;
}

const URLItemsRenderer: React.FC<URLItemsRendererProps> = ({
  items,
  messageId,
  stepIndex,
  isCurrentStep,
  handleLinkClick,
}) => {
  const [animationTick, setAnimationTick] = useState(0);

  useEffect(() => {
    if (items.length > 1 || (isCurrentStep && items.length > 0)) {
      const interval = setInterval(() => {
        setAnimationTick((prev) => prev + 1);
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [items.length, isCurrentStep]);

  return (
    <div
      className={cn(
        'relative max-h-64 overflow-y-auto rounded-xl',
        'bg-gradient-to-br from-background via-primary/5 to-primary/10',
        'dark:from-background dark:via-primary/10 dark:to-primary/5',
        'border border-primary/20 dark:border-primary/30',
        'backdrop-blur-sm',
        'transition-all duration-300',
        'custom-scrollbar',
      )}
      style={{ scrollBehavior: 'smooth' }}
    >
      {/* 头部标识 */}
      <div className="sticky top-0 z-10 px-4 py-2 bg-background/80 backdrop-blur-sm border-b border-primary/10">
        <div className="flex items-center gap-2 text-xs text-foreground/70">
          <Globe className="w-4 h-4 text-primary" />
          {(items.length > 1 || (isCurrentStep && items.length > 0)) && (
            <span className={cn('transition-all duration-500', animationTick % 2 === 0 ? 'opacity-100' : 'opacity-70')}>
              {items.length} URLs
            </span>
          )}
          {isCurrentStep && items.length === 0 && (
            <div className="flex items-center gap-1">
              <div className="w-1 h-1 bg-primary rounded-full animate-pulse" />
              <span className="text-primary">Loading...</span>
            </div>
          )}
        </div>
      </div>

      {/* URL轮播 */}
      <div className="p-3">
        <Carousel orientation="vertical" className="w-full">
          <CarouselContent>
            {items.map((item, itemIndex) => {
              let urlPath = '';
              let hostName = '';
              let faviconUrl = '';

              try {
                const url = new URL(item.url);
                hostName = url.hostname.replace(/^www\./, '');
                const pathname = url.pathname.replace(/^\//, '').replace(/\/$/, '');
                const search = url.search;
                urlPath = pathname || search ? `/${pathname}${search}` : '';

                if (isWebpageUrl(item.url)) {
                  faviconUrl = `https://www.google.com/s2/favicons?domain=${url.hostname}&sz=64`;
                }
              } catch (error) {
                console.warn('Failed to parse URL:', item.url, error);
                hostName = item.url;
                urlPath = '';
              }

              return (
                <CarouselItem key={`${messageId}-url-${stepIndex}-${itemIndex}`}>
                  <div
                    className={cn(
                      'group flex items-center gap-3 p-3 rounded-lg',
                      'bg-background/50',
                      'border border-border/50 hover:border-primary/30',
                      'cursor-pointer transition-all duration-200',
                      'hover:scale-[1.01]',
                      'animate-in slide-in-from-bottom-2 fade-in',
                      'h-full',
                    )}
                    style={{
                      animationDelay: `${itemIndex * 100}ms`,
                      animationDuration: '300ms',
                    }}
                    onClick={() => handleLinkClick(item.url)}
                    title={item.url}
                  >
                    {/* 网站 Logo */}
                    <div className="flex-shrink-0 w-6 h-6 rounded-full overflow-hidden bg-white border border-border/30">
                      {faviconUrl ? (
                        <img
                          src={faviconUrl}
                          width={32}
                          height={32}
                          alt="website logo"
                          className="object-contain w-full h-full"
                          style={{ imageRendering: '-webkit-optimize-contrast' }}
                          onError={(e) => {
                            const img = e.target as HTMLImageElement;
                            const parent = img.parentElement;
                            if (parent) {
                              const backupUrl = `https://s2.googleusercontent.com/s2/favicons?domain_url=${item.url}&sz=32`;
                              if (img.src !== backupUrl) {
                                img.src = backupUrl;
                                return;
                              }
                              parent.innerHTML =
                                '<div class="w-full h-full flex items-center justify-center bg-primary/10"><svg class="w-4 h-4 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="9 9h.01"/><path d="15 9h.01"/></svg></div>';
                            }
                          }}
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center bg-primary/10">
                          <Globe className="w-4 h-4 text-primary" />
                        </div>
                      )}
                    </div>

                    {/* 域名 + 路径 */}
                    <div className="flex-1 min-w-0">
                      <p
                        className={cn(
                          'text-sm font-medium text-foreground/90',
                          'group-hover:text-primary transition-colors duration-200',
                          'truncate',
                        )}
                        title={item.url}
                      >
                        <span>{hostName}</span>
                        {urlPath && <span className="font-normal group-hover:text-primary">{urlPath}</span>}
                      </p>
                    </div>
                  </div>
                </CarouselItem>
              );
            })}
          </CarouselContent>
          {items.length > 3 && (
            <>
              <CarouselPrevious />
              <CarouselNext />
            </>
          )}
        </Carousel>
      </div>
    </div>
  );
};

export default URLItemsRenderer;

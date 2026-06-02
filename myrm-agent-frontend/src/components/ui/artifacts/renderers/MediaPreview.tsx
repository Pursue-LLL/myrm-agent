'use client';

import React, { memo, useMemo, useRef, useEffect, useState, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { cn } from '@/lib/utils/classnameUtils';
import { IMAGE_LAZY_LOAD_MARGIN } from '@/lib/constants/artifact';
import { resolveThemeVars, buildWidgetSrcdoc } from '@/lib/widget-theme-bridge';
import { IconImage, IconFilm, IconHeadphones } from '@/components/ui/icons/PremiumIcons';

interface HtmlPreviewProps {
  /** Remote URL (takes priority) */
  url?: string;
  /** HTML content (used via srcdoc when url is absent) */
  content?: string;
  /** Whether content is still streaming (strips scripts for safe preview) */
  isStreaming?: boolean;
  /** Enable theme bridge injection for AI-generated widgets */
  injectTheme?: boolean;
  /** Enable auto height sync (for inline preview mode) */
  autoHeight?: boolean;
}

const SANDBOX_POLICY = 'allow-scripts';
const MIN_IFRAME_HEIGHT = 100;
const MAX_IFRAME_HEIGHT = 2000;

/** HTML Preview — sandboxed iframe with theme bridge, height sync, and link interception */
export const HtmlPreview: React.FC<HtmlPreviewProps> = memo(
  ({ url, content, isStreaming = false, injectTheme = true, autoHeight = false }) => {
    const [isLoading, setIsLoading] = useState(true);
    const [iframeHeight, setIframeHeight] = useState<number | undefined>(undefined);
    const iframeRef = useRef<HTMLIFrameElement>(null);
    const themeVarsRef = useRef<Record<string, string>>({});

    // Resolve theme variables once on mount and when theme changes
    useEffect(() => {
      themeVarsRef.current = resolveThemeVars();

      const observer = new MutationObserver(() => {
        const newVars = resolveThemeVars();
        themeVarsRef.current = newVars;
        // Notify iframe of theme change via postMessage
        iframeRef.current?.contentWindow?.postMessage({ type: 'widget-theme-update', vars: newVars }, '*');
      });

      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class'],
      });

      return () => observer.disconnect();
    }, []);

    // Build srcdoc from content + theme
    const srcdoc = useMemo(() => {
      if (url || !content) return undefined;
      if (!injectTheme) {
        // No theme injection: wrap in minimal safe HTML
        const safeContent = isStreaming ? content.replace(/<script[\s\S]*?<\/script>/gi, '') : content;
        return safeContent;
      }
      return buildWidgetSrcdoc(content, themeVarsRef.current, isStreaming);
    }, [url, content, isStreaming, injectTheme]);

    // Listen for postMessage events from our own iframe only
    const handleMessage = useCallback(
      (e: MessageEvent) => {
        if (e.source !== iframeRef.current?.contentWindow) return;
        if (!e.data || typeof e.data !== 'object') return;

        if (e.data.type === 'widget-resize' && autoHeight) {
          const h = Math.min(Math.max(e.data.height, MIN_IFRAME_HEIGHT), MAX_IFRAME_HEIGHT);
          setIframeHeight(h);
        }

        if (e.data.type === 'widget-navigate' && typeof e.data.url === 'string') {
          window.open(e.data.url, '_blank', 'noopener,noreferrer');
        }
      },
      [autoHeight],
    );

    useEffect(() => {
      window.addEventListener('message', handleMessage);
      return () => window.removeEventListener('message', handleMessage);
    }, [handleMessage]);

    const handleLoad = useCallback(() => setIsLoading(false), []);

    // URL mode: remote content
    if (url) {
      return (
        <div className="h-full w-full overflow-hidden relative">
          {isLoading && <LoadingOverlay />}
          <iframe
            ref={iframeRef}
            src={url}
            className="w-full h-full border-0 bg-background"
            sandbox={SANDBOX_POLICY}
            title="HTML Preview"
            onLoad={handleLoad}
          />
        </div>
      );
    }

    // Content mode: srcdoc rendering
    if (!srcdoc) {
      return (
        <div className="h-full w-full flex items-center justify-center text-muted-foreground">
          <div className="animate-spin w-6 h-6 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
        </div>
      );
    }

    return (
      <div
        className={cn('w-full overflow-hidden relative', !autoHeight && 'h-full')}
        style={autoHeight && iframeHeight ? { height: iframeHeight } : undefined}
      >
        {isLoading && <LoadingOverlay />}
        <iframe
          ref={iframeRef}
          srcDoc={srcdoc}
          className={cn('w-full border-0 bg-background', autoHeight ? '' : 'h-full')}
          style={autoHeight && iframeHeight ? { height: iframeHeight } : undefined}
          sandbox={SANDBOX_POLICY}
          title="HTML Preview"
          onLoad={handleLoad}
        />
      </div>
    );
  },
);
HtmlPreview.displayName = 'HtmlPreview';

const LoadingOverlay: React.FC = memo(() => (
  <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
    <div className="animate-spin w-6 h-6 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
  </div>
));
LoadingOverlay.displayName = 'LoadingOverlay';

/** 图片预览组件（支持懒加载） */
export const ImagePreview: React.FC<{ url: string; filename: string; errorMessage: string }> = memo(
  ({ url, filename, errorMessage }) => {
    const [isLoaded, setIsLoaded] = React.useState(false);
    const [hasError, setHasError] = React.useState(false);
    const imgRef = useRef<HTMLImageElement>(null);

    React.useEffect(() => {
      const img = imgRef.current;
      if (!img) return;

      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              img.src = url;
              observer.unobserve(img);
            }
          });
        },
        { threshold: 0.1, rootMargin: `${IMAGE_LAZY_LOAD_MARGIN}px` },
      );

      observer.observe(img);
      return () => observer.disconnect();
    }, [url]);

    return (
      <div className="h-full w-full flex items-center justify-center bg-muted/30 p-4">
        {!isLoaded && !hasError && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-full max-w-md aspect-video rounded-lg bg-muted animate-pulse flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-muted-foreground/10" />
            </div>
          </div>
        )}

        {hasError && (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center">
              <IconImage className="w-8 h-8 text-muted-foreground" />
            </div>
            <span className="text-sm">{errorMessage}</span>
          </div>
        )}

        <img
          ref={imgRef}
          alt={filename}
          className={cn(
            'max-w-full max-h-full object-contain rounded-lg shadow-lg transition-opacity duration-300',
            isLoaded ? 'opacity-100' : 'opacity-0',
          )}
          onLoad={() => setIsLoaded(true)}
          onError={() => setHasError(true)}
        />
      </div>
    );
  },
);
ImagePreview.displayName = 'ImagePreview';

/** 视频预览组件（带加载骨架屏） */
export const VideoPreview: React.FC<{ url: string; filename: string; errorMessage: string }> = memo(
  ({ url, filename, errorMessage }) => {
    const [isLoaded, setIsLoaded] = useState(false);
    const [hasError, setHasError] = useState(false);

    const handleLoadedData = useCallback(() => setIsLoaded(true), []);
    const handleError = useCallback(() => setHasError(true), []);

    return (
      <div className="h-full w-full flex items-center justify-center bg-black/5 dark:bg-white/5 p-4">
        {!isLoaded && !hasError && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-full max-w-lg aspect-video rounded-lg bg-muted animate-pulse flex items-center justify-center">
              <div className="flex flex-col items-center gap-2">
                <div className="w-14 h-14 rounded-full bg-muted-foreground/10 flex items-center justify-center">
                  <div className="w-0 h-0 border-l-[12px] border-l-muted-foreground/20 border-y-[8px] border-y-transparent ml-1" />
                </div>
              </div>
            </div>
          </div>
        )}

        {hasError && (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center">
              <IconFilm className="w-8 h-8 text-muted-foreground" />
            </div>
            <span className="text-sm">{errorMessage}</span>
          </div>
        )}

        {!hasError && (
          <video
            src={url}
            controls
            playsInline
            preload="metadata"
            className={cn(
              'max-w-full max-h-full rounded-lg shadow-lg transition-opacity duration-300',
              isLoaded ? 'opacity-100' : 'opacity-0',
            )}
            onLoadedData={handleLoadedData}
            onError={handleError}
          >
            <track kind="captions" label={filename} />
          </video>
        )}
      </div>
    );
  },
);
VideoPreview.displayName = 'VideoPreview';

/** SVG 内联渲染组件（使用 DOMPurify 安全渲染） */
export const SvgPreview: React.FC<{ content: string }> = memo(({ content }) => {
  const sanitizedContent = useMemo(() => {
    return DOMPurify.sanitize(content, {
      USE_PROFILES: { svg: true, svgFilters: true },
      ADD_TAGS: ['use'],
      ADD_ATTR: ['xlink:href'],
    });
  }, [content]);

  return (
    <div
      className="h-full w-full flex items-center justify-center bg-muted/30 p-4 overflow-auto [&>svg]:max-w-full [&>svg]:max-h-full [&>svg]:object-contain"
      dangerouslySetInnerHTML={{ __html: sanitizedContent }}
    />
  );
});
SvgPreview.displayName = 'SvgPreview';

/** 音频预览组件 */
export const AudioPreview: React.FC<{ url: string; filename: string; errorMessage: string }> = memo(
  ({ url, filename, errorMessage }) => {
    const [hasError, setHasError] = useState(false);

    const handleError = useCallback(() => setHasError(true), []);

    return (
      <div className="h-full w-full flex items-center justify-center bg-black/5 dark:bg-white/5 p-8">
        {hasError ? (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center">
              <IconHeadphones className="w-8 h-8 text-muted-foreground" />
            </div>
            <span className="text-sm">{errorMessage}</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-6 w-full max-w-md">
            <div className="w-24 h-24 rounded-full bg-primary/10 flex items-center justify-center shadow-inner">
              <IconHeadphones className="w-12 h-12 text-primary/80" />
            </div>
            <div className="w-full bg-background rounded-full shadow-sm border p-2">
              <audio
                src={url}
                controls
                preload="metadata"
                className="w-full h-10 outline-none"
                onError={handleError}
                title={filename}
              />
            </div>
          </div>
        )}
      </div>
    );
  },
);
AudioPreview.displayName = 'AudioPreview';

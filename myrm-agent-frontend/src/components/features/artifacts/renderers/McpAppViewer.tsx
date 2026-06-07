'use client';

import React, { memo, useRef, useEffect, useState, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { resolveThemeVars } from '@/lib/widget-theme-bridge';
import { fetchWithTimeout } from '@/lib/api';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';
import type { McpAppView } from '@/store/chat/types';

const SANDBOX_POLICY = 'allow-scripts allow-forms';
const MIN_HEIGHT = 120;
const MAX_HEIGHT = 2000;

interface McpAppViewerProps {
  view: McpAppView;
  className?: string;
}

/**
 * MCP Apps (ext-apps) viewer — sandboxed iframe host for MCP server UI resources.
 *
 * Implements the ext-apps host protocol:
 * - Fetches UI content from the MCP server via the backend proxy
 * - Injects host context (theme, locale) via postMessage
 * - Handles app→host messages: notify (toast), openLink, resize
 * - Sends structuredContent from tool results to the embedded app via ontoolresult
 */
export const McpAppViewer: React.FC<McpAppViewerProps> = memo(({ view, className }) => {
  const t = useTranslations('chat.mcpApp');
  const [htmlContent, setHtmlContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [iframeHeight, setIframeHeight] = useState(MIN_HEIGHT);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const themeVarsRef = useRef<Record<string, string>>({});

  // Fetch UI resource from backend proxy
  useEffect(() => {
    let cancelled = false;
    const fetchResource = async () => {
      try {
        const params = new URLSearchParams({
          uri: view.resourceUri,
          server: view.serverName,
        });
        const resp = await fetchWithTimeout(
          `/integrations/mcp/resource?${params.toString()}`,
          {},
          15000,
        );
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const json = await resp.json();
        if (cancelled) return;
        const content = json?.data?.content;
        if (!content) {
          throw new Error('Empty resource content');
        }
        const decoded = atob(content);
        setHtmlContent(decoded);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load MCP App');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    void fetchResource();
    return () => { cancelled = true; };
  }, [view.resourceUri, view.serverName]);

  // Theme bridge
  useEffect(() => {
    themeVarsRef.current = resolveThemeVars();

    const observer = new MutationObserver(() => {
      const newVars = resolveThemeVars();
      themeVarsRef.current = newVars;
      iframeRef.current?.contentWindow?.postMessage(
        { type: 'hostcontextchanged', context: { theme: newVars } },
        '*',
      );
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => observer.disconnect();
  }, []);

  // Send structuredContent to the embedded app after iframe loads
  const handleIframeLoad = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow) return;

    // Send host context (theme, locale)
    iframe.contentWindow.postMessage(
      { type: 'hostcontextchanged', context: { theme: themeVarsRef.current, locale: navigator.language } },
      '*',
    );

    // Send structuredContent as a tool result event (ext-apps ontoolresult)
    if (view.structuredContent) {
      iframe.contentWindow.postMessage(
        { type: 'toolresult', content: view.structuredContent },
        '*',
      );
    }
  }, [view.structuredContent]);

  // Handle messages from the embedded app
  const handleMessage = useCallback(
    (e: MessageEvent) => {
      if (e.source !== iframeRef.current?.contentWindow) return;
      if (!e.data || typeof e.data !== 'object') return;

      const { type } = e.data;

      // app:notify → host toast notification
      if (type === 'notify' || type === 'app:notify') {
        const level = e.data.level ?? 'info';
        const message = typeof e.data.message === 'string' ? e.data.message : '';
        if (message) {
          if (level === 'error') toast.error(message);
          else if (level === 'warning') toast.warning(message);
          else toast.info(message);
        }
      }

      // openLink → open external URL in new tab
      if (type === 'openLink' || type === 'app:openLink' || type === 'widget-navigate') {
        const url = typeof e.data.url === 'string' ? e.data.url : '';
        if (url) {
          window.open(url, '_blank', 'noopener,noreferrer');
        }
      }

      // resize → auto-height adjustment
      if (type === 'resize' || type === 'widget-resize') {
        const h = Math.min(Math.max(Number(e.data.height) || MIN_HEIGHT, MIN_HEIGHT), MAX_HEIGHT);
        setIframeHeight(h);
      }
    },
    [],
  );

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  if (error) {
    return (
      <div className={cn('rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive', className)}>
        {t('loadFailed', { error })}
      </div>
    );
  }

  if (isLoading || !htmlContent) {
    return (
      <div className={cn('rounded-lg border bg-muted/30 p-6 flex items-center justify-center', className)}>
        <div className="animate-spin w-5 h-5 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
        <span className="ml-2 text-sm text-muted-foreground">{t('loading')}</span>
      </div>
    );
  }

  return (
    <div
      className={cn('rounded-lg border overflow-hidden', className)}
      style={{ height: iframeHeight }}
    >
      <iframe
        ref={iframeRef}
        srcDoc={htmlContent}
        className="w-full h-full border-0 bg-background"
        sandbox={SANDBOX_POLICY}
        title={t('title', { server: view.serverName })}
        onLoad={handleIframeLoad}
      />
    </div>
  );
});
McpAppViewer.displayName = 'McpAppViewer';

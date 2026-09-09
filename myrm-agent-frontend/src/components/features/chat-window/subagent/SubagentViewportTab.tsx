'use client';

/**
 * [INPUT]
 * @/store/chat/useSubagentStore::SubagentNode (POS: Multi-agent execution tree and stream state store)
 * @/store/useBrowserInspectorStore::useBrowserInspectorStore (POS: Browser Inspector state management; selectScopedBrowserViewData)
 * @/store/useChatStore::useChatStore (POS: Active chat session identification)
 *
 * [OUTPUT]
 * SubagentViewportTab: Sandboxed browser live peek panel and terminal snapshot view for subagents.
 *
 * [POS]
 * Subagent inspection surface. Displays subagent browser snapshots, lightboxed zoom, and click-to-control sandbox desktop takeover.
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Globe,
  MonitorPlay,
  Maximize2,
  Minimize2,
  Copy,
  Check,
  Terminal,
  Clock,
  Activity,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { SubagentNode } from '@/store/chat/useSubagentStore';
import useBrowserInspectorStore, { selectScopedBrowserViewData } from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';

interface SubagentViewportTabProps {
  node: SubagentNode;
  chatId?: string;
}

interface ViewportData {
  screenshotUrl: string;
  source: 'stream_output' | 'scoped_inspector';
  url?: string;
  title?: string;
  isLive: boolean;
}

export const SubagentViewportTab: React.FC<SubagentViewportTabProps> = ({ node, chatId }) => {
  const [isZoomed, setIsZoomed] = useState(false);
  const [hasCopied, setHasCopied] = useState(false);

  useEffect(() => {
    if (!isZoomed) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsZoomed(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isZoomed]);

  const activeChatId = useChatStore((state) => state.chatId?.trim() ?? '');
  const effectiveChatId = chatId?.trim() || activeChatId;

  const { viewData, terminalViewData, isBrowserActive } = useBrowserInspectorStore();
  const scopedInspectorView = useMemo(
    () => selectScopedBrowserViewData(viewData ?? terminalViewData, effectiveChatId),
    [viewData, terminalViewData, effectiveChatId],
  );

  const viewportData = useMemo<ViewportData | null>(() => {
    // 1. Inspect stream entries in reverse chronological order for screenshots
    const stream = node.stream || [];
    for (let i = stream.length - 1; i >= 0; i--) {
      const entry = stream[i];
      if (entry?.text) {
        // Direct data-uri
        const b64Match = entry.text.match(/data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+/);
        if (b64Match) {
          return {
            screenshotUrl: b64Match[0],
            source: 'stream_output',
            isLive: false,
          };
        }
        // JSON payload containing screenshot / screenshot_base64
        if (entry.text.includes('screenshot_base64') || entry.text.includes('"screenshot"')) {
          try {
            const parsed = JSON.parse(entry.text) as Record<string, unknown>;
            const raw = parsed.screenshot_base64 || parsed.screenshot;
            if (typeof raw === 'string' && raw.length > 20) {
              const src = raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
              return {
                screenshotUrl: src,
                source: 'stream_output',
                url: typeof parsed.url === 'string' ? parsed.url : undefined,
                title: typeof parsed.title === 'string' ? parsed.title : undefined,
                isLive: false,
              };
            }
          } catch {
            // Non-json stream text; continue
          }
        }
      }
    }

    // 2. Fallback to scoped inspector view if subagent used browser/web tools or is actively interacting
    const isBrowserRelated =
      Boolean(node.last_tool && (node.last_tool.includes('browser') || node.last_tool.includes('desktop'))) ||
      Boolean(node.agent_type && (node.agent_type.includes('browser') || node.agent_type.includes('web'))) ||
      stream.some((s) => s.kind === 'tool' && (s.text.toLowerCase().includes('browser') || s.text.toLowerCase().includes('navigate')));

    if ((isBrowserRelated || node.status === 'running') && scopedInspectorView?.screenshotBase64) {
      return {
        screenshotUrl: `data:${scopedInspectorView.mimeType};base64,${scopedInspectorView.screenshotBase64}`,
        source: 'scoped_inspector',
        url: scopedInspectorView.pageUrl,
        title: scopedInspectorView.pageTitle,
        isLive: isBrowserActive,
      };
    }

    return null;
  }, [node.stream, node.last_tool, node.agent_type, node.status, scopedInspectorView, isBrowserActive]);

  const handleOpenDesktop = () => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('open_visual_desktop'));
      toast.info('正在切换至沙箱图形桌面 (Grok click-to-control)');
    }
  };

  const handleCopyUrl = (url: string) => {
    if (typeof navigator !== 'undefined') {
      navigator.clipboard.writeText(url);
      setHasCopied(true);
      toast.success('URL 已复制');
      setTimeout(() => setHasCopied(false), 2000);
    }
  };

  if (!viewportData) {
    return (
      <div
        data-testid="subagent-viewport-empty"
        className="flex flex-col items-center justify-center p-8 rounded-xl border border-dashed border-border/80 bg-muted/20 text-center space-y-4"
      >
        <div className="p-3 rounded-full bg-muted/60 text-muted-foreground">
          <Terminal className="w-8 h-8 opacity-70" />
        </div>
        <div className="space-y-1">
          <h4 className="text-sm font-semibold text-foreground">纯文本/代码任务视口</h4>
          <p className="text-xs text-muted-foreground max-w-sm">
            当前子任务为纯文本或代码任务，尚未产生独立的沙箱浏览器快照。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleOpenDesktop}
          data-testid="subagent-viewport-open-desktop-btn"
          className="text-xs gap-1.5"
        >
          <MonitorPlay className="w-3.5 h-3.5 text-primary" />
          <span>打开沙箱图形桌面窥视</span>
        </Button>
      </div>
    );
  }

  return (
    <div data-testid="subagent-viewport-active" className="space-y-3">
      {/* Top Bar with URL & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg border bg-muted/30">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Badge
            variant="outline"
            className={cn(
              'text-[10px] font-medium gap-1 shrink-0',
              viewportData.isLive
                ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                : 'border-amber-500/30 text-amber-600 dark:text-amber-400 bg-amber-500/10',
            )}
          >
            {viewportData.isLive ? (
              <>
                <Activity className="w-3 h-3 animate-pulse" />
                <span>Live</span>
              </>
            ) : (
              <>
                <Clock className="w-3 h-3" />
                <span>Snapshot</span>
              </>
            )}
          </Badge>

          {viewportData.url ? (
            <div className="flex items-center gap-1 min-w-0 text-xs font-mono bg-background/80 px-2 py-1 rounded border border-border/60">
              <Globe className="w-3 h-3 text-muted-foreground shrink-0" />
              <span className="truncate max-w-[260px] select-all" title={viewportData.url}>
                {viewportData.url}
              </span>
              <button
                type="button"
                onClick={() => {
                  if (viewportData.url) {
                    handleCopyUrl(viewportData.url);
                  }
                }}
                className="p-0.5 text-muted-foreground hover:text-foreground transition-colors ml-1"
                title="复制 URL"
              >
                {hasCopied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
              </button>
              <a
                href={viewportData.url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-0.5 text-muted-foreground hover:text-foreground transition-colors"
                title="新标签页打开"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground truncate">
              {viewportData.title || '沙箱浏览器视口'}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setIsZoomed(!isZoomed)}
            className="h-7 px-2 text-xs gap-1"
            title={isZoomed ? '恢复尺寸' : '全屏缩放'}
          >
            {isZoomed ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{isZoomed ? '缩小' : '放大'}</span>
          </Button>
          <Button
            size="sm"
            variant="default"
            onClick={handleOpenDesktop}
            data-testid="subagent-viewport-takeover-btn"
            className="h-7 px-2.5 text-xs gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <MonitorPlay className="w-3.5 h-3.5" />
            <span>接管控制</span>
          </Button>
        </div>
      </div>

      {/* Snapshot / Live Viewport Image Display */}
      <div
        data-testid="subagent-viewport-image-container"
        className={cn(
          'relative rounded-xl border border-border/80 overflow-hidden bg-black/5 dark:bg-black/40 flex items-center justify-center transition-all duration-200',
          isZoomed
            ? 'fixed inset-4 z-50 p-4 bg-background/95 backdrop-blur-md shadow-2xl'
            : 'w-full max-h-[520px]',
        )}
      >
        {isZoomed && (
          <>
            <button
              type="button"
              data-testid="subagent-viewport-backdrop"
              onClick={() => setIsZoomed(false)}
              className="absolute inset-0 w-full h-full bg-transparent border-0 cursor-zoom-out"
              aria-label="退出放大"
            />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsZoomed(false)}
              className="absolute top-4 right-4 z-10 h-8 px-3 text-xs gap-1 shadow-md"
            >
              <Minimize2 className="w-3.5 h-3.5" />
              <span>退出放大</span>
            </Button>
          </>
        )}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={viewportData.screenshotUrl}
          alt={viewportData.title || 'Subagent Viewport Preview'}
          className={cn(
            'object-contain rounded-lg transition-transform duration-150',
            isZoomed ? 'relative z-10 w-auto h-auto max-w-full max-h-full cursor-default' : 'w-full h-auto max-h-[480px]',
          )}
          draggable={false}
        />
      </div>
    </div>
  );
};

export default React.memo(SubagentViewportTab);

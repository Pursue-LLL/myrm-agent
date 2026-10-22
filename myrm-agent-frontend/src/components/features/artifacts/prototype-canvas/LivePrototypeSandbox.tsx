/**
 * [INPUT]
 * - prototypeCanvasTypes: PrototypeViewport
 *
 * [OUTPUT]
 * - LivePrototypeSandbox: Sandboxed interactive previewer for UI prototypes with click-and-comment element picking
 *
 * [POS]
 * Secure interactive sandbox for Intent-to-Prototype Canvas (Item 46 P0).
 * Strictly under 320 lines. Zero `any`.
 */

'use client';

import React, { memo, useRef, useEffect, useMemo, useCallback } from 'react';
import type { PrototypeViewport } from './prototypeCanvasTypes';

interface SelectedElementPayload {
  tag: string;
  selector: string;
  rect: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

interface LivePrototypeSandboxProps {
  content: string; // HTML source or synthesized intent markup
  viewport: PrototypeViewport;
  isAnnotating: boolean;
  onElementSelect?: (element: SelectedElementPayload) => void;
  className?: string;
}

const VIEWPORT_WIDTHS: Record<PrototypeViewport, string> = {
  desktop: 'w-full max-w-[1200px]',
  tablet: 'w-[768px] max-w-full',
  mobile: 'w-[375px] max-w-full',
};

const BASE_HEAD_TEMPLATE = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 16px;
      background-color: #ffffff;
      color: #1e293b;
    }
    .myrm-pick-hover {
      outline: 2px dashed #3b82f6 !important;
      outline-offset: 2px !important;
      cursor: crosshair !important;
    }
  </style>
</head>
<body>
`;

export const LivePrototypeSandbox: React.FC<LivePrototypeSandboxProps> = memo(({
  content,
  viewport,
  isAnnotating,
  onElementSelect,
  className = '',
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Compile full iframe HTML with element-picking inspector shim
  const compiledSrcDoc = useMemo(() => {
    let bodyMarkup = content;
    const isFullHtml = /<html[\s\S]*>/i.test(content);

    const inspectorScript = `
    <script>
      (function() {
        var isAnnotating = ${isAnnotating ? 'true' : 'false'};
        var lastHovered = null;

        window.addEventListener('message', function(event) {
          if (event.data && event.data.type === 'MYRM_SET_ANNOTATING') {
            isAnnotating = !!event.data.enabled;
            if (!isAnnotating && lastHovered) {
              lastHovered.classList.remove('myrm-pick-hover');
              lastHovered = null;
            }
          }
        });

        document.addEventListener('mouseover', function(e) {
          if (!isAnnotating) { return; }
          if (lastHovered && lastHovered !== e.target) {
            lastHovered.classList.remove('myrm-pick-hover');
          }
          lastHovered = e.target;
          if (lastHovered) {
            lastHovered.classList.add('myrm-pick-hover');
          }
        }, true);

        document.addEventListener('mouseout', function(e) {
          if (!isAnnotating) { return; }
          if (e.target && e.target.classList) {
            e.target.classList.remove('myrm-pick-hover');
          }
        }, true);

        document.addEventListener('click', function(e) {
          if (!isAnnotating) { return; }
          e.preventDefault();
          e.stopPropagation();

          var target = e.target;
          var tag = target.tagName.toLowerCase();
          var selector = tag;
          if (target.id) {
            selector = '#' + target.id;
          } else if (target.className && typeof target.className === 'string') {
            var firstClass = target.className.trim().split(/\\s+/)[0];
            if (firstClass && !firstClass.startsWith('myrm-')) {
              selector = '.' + firstClass;
            }
          }

          var rect = target.getBoundingClientRect();
          window.parent.postMessage({
            type: 'MYRM_PROTOTYPE_PICK',
            tag: tag,
            selector: selector,
            rect: {
              x: rect.left,
              y: rect.top,
              width: rect.width,
              height: rect.height
            }
          }, '*');
        }, true);
      })();
    </script>
    `;

    if (isFullHtml) {
      return bodyMarkup.replace('</body>', `${inspectorScript}</body>`);
    }

    if (!bodyMarkup.trim()) {
      bodyMarkup = `
        <div class="p-8 text-center text-slate-400">
          <p class="text-sm">（暂无交互原型内容，请等待 Agent 生成）</p>
        </div>
      `;
    }

    return `${BASE_HEAD_TEMPLATE}${bodyMarkup}${inspectorScript}</body></html>`;
  }, [content, isAnnotating]);

  // Handle postMessage events from the sandboxed iframe
  const handleWindowMessage = useCallback((event: MessageEvent) => {
    if (!event.data || event.data.type !== 'MYRM_PROTOTYPE_PICK') {
      return;
    }

    if (onElementSelect && event.data.selector && event.data.rect) {
      onElementSelect({
        tag: String(event.data.tag || 'element'),
        selector: String(event.data.selector),
        rect: {
          x: Number(event.data.rect.x || 0),
          y: Number(event.data.rect.y || 0),
          width: Number(event.data.rect.width || 0),
          height: Number(event.data.rect.height || 0),
        },
      });
    }
  }, [onElementSelect]);

  useEffect(() => {
    window.addEventListener('message', handleWindowMessage);
    return () => {
      window.removeEventListener('message', handleWindowMessage);
    };
  }, [handleWindowMessage]);

  // Sync annotating state with iframe via postMessage
  useEffect(() => {
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        {
          type: 'MYRM_SET_ANNOTATING',
          enabled: isAnnotating,
        },
        '*'
      );
    }
  }, [isAnnotating]);

  return (
    <div
      data-testid="live-prototype-sandbox-root"
      className={`h-full w-full flex justify-center items-start overflow-auto p-4 transition-all ${className}`}
    >
      <div
        data-testid={`prototype-frame-${viewport}`}
        className={`${VIEWPORT_WIDTHS[viewport]} h-[820px] max-h-full bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden flex flex-col transition-all relative`}
      >
        {/* Device Frame Header */}
        <div className="h-8 bg-slate-100 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700/60 px-3 flex items-center justify-between shrink-0 select-none">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-400 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />
          </div>
          <div className="text-[11px] font-mono text-slate-400 truncate max-w-[200px]">
            prototype://live-canvas/{viewport}
          </div>
          <div className="w-10" />
        </div>

        {/* Sandboxed Iframe Container */}
        <iframe
          ref={iframeRef}
          data-testid="prototype-sandboxed-iframe"
          title="Interactive Prototype Canvas"
          srcDoc={compiledSrcDoc}
          sandbox="allow-scripts allow-forms"
          className="w-full flex-1 border-none bg-white select-text"
        />
      </div>
    </div>
  );
});

LivePrototypeSandbox.displayName = 'LivePrototypeSandbox';

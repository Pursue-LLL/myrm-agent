/**
 * [INPUT]
 * - canvasSecurityTypes: CanvasViewerProps, CanvasEgressRequest
 * - CanvasSecurityBridge: compileSandboxedHtml, STRICT_SANDBOX_POLICY, validateInboundCanvasMessage
 * - useCanvasGatingStore: useCanvasGatingStore
 *
 * [OUTPUT]
 * - CanvasViewer: Strict sandboxed iframe viewer with interactive network egress gating
 *
 * [POS]
 * Secure Canvas host component for rich interactive HTML/Canvas artifacts (Item 44 P0).
 * Strictly under 260 lines. Zero `any`.
 */

'use client';

import React, { memo, useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { ShieldCheck, ShieldAlert, Globe, Lock, Check, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  compileSandboxedHtml,
  STRICT_SANDBOX_POLICY,
  validateInboundCanvasMessage,
} from './CanvasSecurityBridge';
import { useCanvasGatingStore } from './useCanvasGatingStore';
import type { CanvasViewerProps } from './canvasSecurityTypes';

export const CanvasViewer: React.FC<CanvasViewerProps> = memo(({
  content,
  title = 'Canvas Artifact',
  className = '',
  onSecurityEvent,
}) => {
  const t = useTranslations('canvasSecurity');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isLoaded, setIsLoaded] = useState(false);

  const {
    pendingRequests,
    registerEgressRequest,
    approveRequest,
    denyRequest,
    auditLogs,
  } = useCanvasGatingStore();

  const compiledHtml = useMemo(() => {
    return compileSandboxedHtml(content);
  }, [content]);

  // Reply to iframe via postMessage with egress decision
  const replyToIframe = useCallback((requestId: string, allowed: boolean) => {
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        {
          type: 'canvas-egress-response',
          requestId,
          allowed,
        },
        '*'
      );
    }
  }, []);

  const handleApprove = useCallback(
    (requestId: string, trustDomain: boolean) => {
      approveRequest(requestId, trustDomain);
      replyToIframe(requestId, true);
    },
    [approveRequest, replyToIframe]
  );

  const handleDeny = useCallback(
    (requestId: string) => {
      denyRequest(requestId);
      replyToIframe(requestId, false);
    },
    [denyRequest, replyToIframe]
  );

  // Listen for inbound messages from the sandboxed iframe
  useEffect(() => {
    const handleWindowMessage = (event: MessageEvent) => {
      const parsed = validateInboundCanvasMessage(
        event,
        iframeRef.current?.contentWindow ?? null
      );

      if (!parsed) {
        return;
      }

      if (parsed.type === 'canvas-egress-request' && parsed.url && parsed.domain) {
        const result = registerEgressRequest({
          url: parsed.url,
          domain: parsed.domain,
          method: parsed.method ?? 'GET',
        });

        if (result.allowed) {
          replyToIframe(parsed.requestId ?? '', true);
        }

        if (onSecurityEvent) {
          onSecurityEvent({
            id: result.requestId,
            type: result.allowed ? 'egress-allowed' : 'egress-requested',
            detail: `${parsed.method ?? 'GET'} ${parsed.url}`,
            domain: parsed.domain,
            timestamp: Date.now(),
          });
        }
      }
    };

    window.addEventListener('message', handleWindowMessage);
    return () => {
      window.removeEventListener('message', handleWindowMessage);
    };
  }, [registerEgressRequest, replyToIframe, onSecurityEvent]);

  const hasPendingRequests = pendingRequests.length > 0;
  const currentPending = pendingRequests[0];

  return (
    <div className={`relative flex flex-col h-full w-full overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 ${className}`}>
      {/* Security Status Header Bar */}
      <header className="flex h-9 shrink-0 items-center justify-between border-b border-slate-200/80 bg-slate-50/90 px-3 text-xs backdrop-blur-xs dark:border-slate-800/80 dark:bg-slate-900/90">
        <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
          <Lock className="h-3.5 w-3.5 text-slate-400" />
          <span className="font-semibold truncate max-w-48">{title}</span>
        </div>

        <div className="flex items-center gap-2.5">
          {hasPendingRequests ? (
            <div className="flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
              <ShieldAlert className="h-3 w-3" />
              <span>{t('pendingEgressBadge', { count: pendingRequests.length })}</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
              <ShieldCheck className="h-3 w-3" />
              <span>{t('sandboxedIsolatedBadge')}</span>
            </div>
          )}
          <span className="text-[10px] text-slate-400">
            {t('auditCount', { count: auditLogs.length })}
          </span>
        </div>
      </header>

      {/* Interactive Script & Network Egress Gate Alert Banner */}
      {currentPending && (
        <aside
          role="alert"
          aria-label="Network egress authorization alert"
          className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5 border-b border-amber-200 bg-amber-50/95 p-3 text-xs text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/60 dark:text-amber-100 animate-in fade-in slide-in-from-top-1"
        >
          <div className="flex items-center gap-2 min-w-0">
            <Globe className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <div className="truncate">
              <span className="font-semibold">{t('egressPromptTitle')}: </span>
              <span className="font-mono text-amber-800 dark:text-amber-200 underline decoration-amber-400">
                {currentPending.domain}
              </span>
              <span className="ml-1 text-[11px] text-amber-600 dark:text-amber-400 truncate">
                ({currentPending.method} {currentPending.url})
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={() => handleDeny(currentPending.id)}
              className="flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-colors"
            >
              <X className="h-3 w-3 text-red-500" />
              <span>{t('blockEgress')}</span>
            </button>
            <button
              type="button"
              onClick={() => handleApprove(currentPending.id, false)}
              className="flex items-center gap-1 rounded-md bg-amber-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-amber-700 transition-colors shadow-xs"
            >
              <Check className="h-3 w-3" />
              <span>{t('allowOnce')}</span>
            </button>
            <button
              type="button"
              onClick={() => handleApprove(currentPending.id, true)}
              className="flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 transition-colors shadow-xs"
            >
              <Check className="h-3 w-3" />
              <span>{t('alwaysAllowDomain')}</span>
            </button>
          </div>
        </aside>
      )}

      {/* Isolated Sandboxed Iframe Container */}
      <div className="relative flex-1 w-full h-full bg-slate-50 dark:bg-slate-900">
        {!isLoaded && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-slate-950/70 z-10">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
          </div>
        )}
        <iframe
          ref={iframeRef}
          srcDoc={compiledHtml}
          sandbox={STRICT_SANDBOX_POLICY}
          title={title}
          onLoad={() => setIsLoaded(true)}
          className="h-full w-full border-0 bg-transparent"
        />
      </div>
    </div>
  );
});

CanvasViewer.displayName = 'CanvasViewer';
export default CanvasViewer;

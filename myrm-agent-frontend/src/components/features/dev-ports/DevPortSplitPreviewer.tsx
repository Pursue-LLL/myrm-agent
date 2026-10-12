/**
 * [INPUT]
 * @/services/devPorts::DevPortInfo, createDevPortTunnel
 * @/components/features/icons/PremiumIcons (IconGlobe, IconExternalLink, IconRefresh, IconMonitor, IconCopy, IconCheck, IconX, IconChevronDown, IconChevronUp)
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - DevPortSplitPreviewer: Slide-over split preview panel for sandbox web service with viewport controls & live hot reload
 *
 * [POS]
 * Split drawer component for DevPortsListeningBarAndSandboxServicePreviewHub.
 * Single file < 350 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import type { DevPortInfo } from '@/services/devPorts';
import * as devPortsService from '@/services/devPorts';
import {
  IconGlobe,
  IconExternalLink,
  IconRefresh,
  IconMonitor,
  IconCopy,
  IconCheck,
  IconX,
  IconChevronDown,
  IconChevronUp,
} from '@/components/features/icons/PremiumIcons';

export type SplitViewportMode = 'desktop' | 'tablet' | 'mobile';

export interface DevPortSplitPreviewerProps {
  isOpen?: boolean;
  activePort?: DevPortInfo | null;
  onClose?: () => void;
}

const VIEWPORT_CONTAINER_WIDTHS: Record<SplitViewportMode, string> = {
  desktop: 'w-full',
  tablet: 'w-[768px] max-w-full',
  mobile: 'w-[375px] max-w-full',
};

export const DevPortSplitPreviewer: React.FC<DevPortSplitPreviewerProps> = ({
  isOpen: controlledIsOpen,
  activePort: controlledPort,
  onClose: controlledOnClose,
}) => {
  const t = useTranslations('devPorts');
  const [internalIsOpen, setInternalIsOpen] = useState<boolean>(false);
  const [currentPort, setCurrentPort] = useState<DevPortInfo | null>(null);
  const [viewport, setViewport] = useState<SplitViewportMode>('desktop');
  const [tunnelUrl, setTunnelUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [iframeKey, setIframeKey] = useState<number>(0);
  const [isConsoleOpen, setIsConsoleOpen] = useState<boolean>(false);
  const [isCreatingTunnel, setIsCreatingTunnel] = useState<boolean>(false);

  const isControlled = controlledIsOpen !== undefined;
  const isPanelOpen = isControlled ? controlledIsOpen : internalIsOpen;
  const port = isControlled ? controlledPort ?? null : currentPort;

  // Listen to global open/close events when uncontrolled or globally mounted
  useEffect(() => {
    const handleOpenEvent = (e: Event) => {
      const customEvent = e as CustomEvent<DevPortInfo>;
      if (customEvent.detail) {
        setCurrentPort(customEvent.detail);
        setInternalIsOpen(true);
      }
    };

    const handleCloseEvent = () => {
      setInternalIsOpen(false);
    };

    window.addEventListener('myrm:open-dev-port-preview', handleOpenEvent);
    window.addEventListener('myrm:close-dev-port-preview', handleCloseEvent);

    return () => {
      window.removeEventListener('myrm:open-dev-port-preview', handleOpenEvent);
      window.removeEventListener('myrm:close-dev-port-preview', handleCloseEvent);
    };
  }, []);

  useEffect(() => {
    if (port?.tunnel_url) {
      setTunnelUrl(port.tunnel_url);
    } else {
      setTunnelUrl(null);
    }
  }, [port]);

  const handleClose = useCallback(() => {
    if (controlledOnClose) {
      controlledOnClose();
    } else {
      setInternalIsOpen(false);
    }
  }, [controlledOnClose]);

  const handleRefresh = useCallback(() => {
    setIframeKey((prev) => prev + 1);
  }, []);

  const handleCopyTunnel = useCallback(async () => {
    if (!port) {
      return;
    }
    try {
      let targetUrl = tunnelUrl;
      if (!targetUrl) {
        setIsCreatingTunnel(true);
        const resp = await devPortsService.createDevPortTunnel(port.port);
        targetUrl = resp.tunnel_url;
        setTunnelUrl(targetUrl);
      }
      if (targetUrl) {
        await navigator.clipboard.writeText(targetUrl);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // Ignore clipboard error
    } finally {
      setIsCreatingTunnel(false);
    }
  }, [port, tunnelUrl]);

  if (!isPanelOpen || !port) {
    return null;
  }

  const previewTargetUrl = tunnelUrl || port.url;

  return (
    <aside
      aria-label={t('splitPreviewerTitle')}
      data-testid="dev-port-split-previewer"
      className="fixed inset-y-0 right-0 z-50 flex flex-col w-full sm:w-[540px] md:w-[680px] lg:w-[780px] bg-zinc-950/95 backdrop-blur-xl border-l border-zinc-800/80 shadow-2xl transition-all duration-300 ease-out animate-in slide-in-from-right"
    >
      {/* Header bar */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/80 bg-zinc-900/60">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-2.5 w-2.5 relative flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
          </span>
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-1.5 truncate">
              <span className="font-semibold text-zinc-100 text-sm">{port.process_name}</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-300 border border-zinc-700/60">
                :{port.port}
              </span>
            </div>
            <span className="text-[11px] text-zinc-400 truncate font-mono">{previewTargetUrl}</span>
          </div>
        </div>

        {/* Viewport switchers */}
        <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 p-0.5 rounded-lg">
          <button
            type="button"
            onClick={() => setViewport('desktop')}
            title={t('viewportDesktop')}
            aria-label={t('viewportDesktop')}
            className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
              viewport === 'desktop'
                ? 'bg-zinc-800 text-zinc-100 font-medium shadow-xs'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <IconMonitor className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setViewport('tablet')}
            title={t('viewportTablet')}
            aria-label={t('viewportTablet')}
            className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
              viewport === 'tablet'
                ? 'bg-zinc-800 text-zinc-100 font-medium shadow-xs'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <span className="text-[10px] font-mono font-medium">768</span>
          </button>
          <button
            type="button"
            onClick={() => setViewport('mobile')}
            title={t('viewportMobile')}
            aria-label={t('viewportMobile')}
            className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
              viewport === 'mobile'
                ? 'bg-zinc-800 text-zinc-100 font-medium shadow-xs'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <span className="text-[10px] font-mono font-medium">375</span>
          </button>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleRefresh}
            aria-label={t('refreshAriaLabel')}
            title={t('refreshAriaLabel')}
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors cursor-pointer"
          >
            <IconRefresh className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={handleCopyTunnel}
            disabled={isCreatingTunnel}
            aria-label={copied ? t('tunnelCopied') : t('copyTunnel')}
            title={tunnelUrl ? t('copyTunnel') : t('createTunnel')}
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors cursor-pointer"
          >
            {copied ? (
              <IconCheck className="w-4 h-4 text-emerald-400" />
            ) : (
              <IconCopy className="w-4 h-4" />
            )}
          </button>

          <a
            href={previewTargetUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t('openInNewTab')}
            title={t('openInNewTab')}
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors"
          >
            <IconExternalLink className="w-4 h-4" />
          </a>

          <button
            type="button"
            onClick={handleClose}
            aria-label={t('closeAriaLabel')}
            title={t('closeAriaLabel')}
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors cursor-pointer ml-1"
          >
            <IconX className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main preview canvas */}
      <main className="flex-1 relative overflow-auto bg-zinc-950 flex flex-col items-center p-2">
        <div
          className={`h-full transition-all duration-200 border border-zinc-800/80 rounded-lg overflow-hidden bg-white shadow-lg ${VIEWPORT_CONTAINER_WIDTHS[viewport]}`}
        >
          <iframe
            key={iframeKey}
            src={previewTargetUrl}
            title={`${port.process_name} live preview`}
            className="w-full h-full border-0"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          />
        </div>
      </main>

      {/* Footer console drawer toggle */}
      <footer className="border-t border-zinc-800/80 bg-zinc-900/70">
        <button
          type="button"
          onClick={() => setIsConsoleOpen((prev) => !prev)}
          className="w-full flex items-center justify-between px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40 transition-colors cursor-pointer"
        >
          <span className="font-mono flex items-center gap-2">
            <IconGlobe className="w-3.5 h-3.5 text-zinc-500" />
            {t('consoleDrawerTitle')}
            <span className="text-[10px] text-emerald-400 font-sans">({t('listening')})</span>
          </span>
          {isConsoleOpen ? (
            <IconChevronDown className="w-3.5 h-3.5" />
          ) : (
            <IconChevronUp className="w-3.5 h-3.5" />
          )}
        </button>

        {isConsoleOpen && (
          <div
            data-testid="dev-port-console-drawer"
            className="px-4 py-2 text-xs font-mono bg-zinc-950 text-zinc-300 border-t border-zinc-800/50 max-h-36 overflow-y-auto space-y-1"
          >
            <div className="text-zinc-500 text-[11px]">
              [{port.created_at}] Service started on port {port.port} ({port.protocol})
            </div>
            <div className="text-emerald-400/90 text-[11px]">
              &gt; Ready: {previewTargetUrl}
            </div>
            {port.pid && (
              <div className="text-zinc-500 text-[11px]">
                &gt; Process PID: {port.pid} | Process: {port.process_name}
              </div>
            )}
          </div>
        )}
      </footer>
    </aside>
  );
};

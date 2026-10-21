/**
 * [INPUT]
 * @/services/devPorts::DevPortInfo, closeDevPort, createDevPortTunnel
 * @/components/features/icons/PremiumIcons (IconGlobe, IconExternalLink, IconRefresh, IconMonitor, IconCopy, IconCheck, IconTrash, IconX)
 * react-i18next::useTranslation
 *
 * [OUTPUT]
 * - DevPortPreviewModal: Semantic dialog modal for sandbox web service live preview with viewport switching & tunneling
 *
 * [POS]
 * Feature component for DevPortsListeningBarAndServicePreviewHub.
 * Single file < 250 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type { DevPortInfo } from '@/services/devPorts';
import { closeDevPort, createDevPortTunnel } from '@/services/devPorts';
import {
  IconGlobe,
  IconExternalLink,
  IconRefresh,
  IconMonitor,
  IconCopy,
  IconCheck,
  IconTrash,
  IconX,
} from '@/components/features/icons/PremiumIcons';

export type ViewportMode = 'desktop' | 'tablet' | 'mobile';

export interface DevPortPreviewModalProps {
  isOpen: boolean;
  portInfo: DevPortInfo | null;
  onClose: () => void;
  onPortTerminated?: (port: number) => void;
}

const VIEWPORT_WIDTHS: Record<ViewportMode, string> = {
  desktop: 'w-full',
  tablet: 'w-[768px]',
  mobile: 'w-[375px]',
};

export const DevPortPreviewModal: React.FC<DevPortPreviewModalProps> = ({
  isOpen,
  portInfo,
  onClose,
  onPortTerminated,
}) => {
  const t = useTranslations('devPorts');
  const dialogRef = useRef<HTMLDialogElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const [viewport, setViewport] = useState<ViewportMode>('desktop');
  const [tunnelUrl, setTunnelUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [isTerminating, setIsTerminating] = useState<boolean>(false);
  const [iframeKey, setIframeKey] = useState<number>(0);

  useEffect(() => {
    if (portInfo?.tunnel_url) {
      setTunnelUrl(portInfo.tunnel_url);
    } else {
      setTunnelUrl(null);
    }
  }, [portInfo]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (isOpen) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else {
      if (dialog.open) {
        dialog.close();
      }
    }
  }, [isOpen]);

  const handleRefresh = useCallback(() => {
    setIframeKey((prev) => prev + 1);
  }, []);

  const handleCopyTunnel = useCallback(async () => {
    if (!portInfo) {
      return;
    }
    try {
      let targetUrl = tunnelUrl;
      if (!targetUrl) {
        const resp = await createDevPortTunnel(portInfo.port);
        targetUrl = resp.tunnel_url;
        setTunnelUrl(targetUrl);
      }
      await navigator.clipboard.writeText(targetUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard error
    }
  }, [portInfo, tunnelUrl]);

  const handleTerminate = useCallback(async () => {
    if (!portInfo || isTerminating) {
      return;
    }
    try {
      setIsTerminating(true);
      await closeDevPort(portInfo.port);
      onPortTerminated?.(portInfo.port);
      onClose();
    } finally {
      setIsTerminating(false);
    }
  }, [portInfo, isTerminating, onPortTerminated, onClose]);

  const handleOpenNewTab = useCallback(() => {
    if (!portInfo) {
      return;
    }
    const targetUrl = tunnelUrl || portInfo.url;
    window.open(targetUrl, '_blank', 'noopener,noreferrer');
  }, [portInfo, tunnelUrl]);

  if (!isOpen || !portInfo) {
    return null;
  }

  const activeUrl = tunnelUrl || portInfo.url;

  return (
    <dialog
      ref={dialogRef}
      onCancel={onClose}
      className="fixed inset-0 m-auto z-50 flex flex-col h-[90vh] w-[92vw] max-w-6xl rounded-2xl border border-zinc-200/80 bg-white dark:border-zinc-800 dark:bg-zinc-950 p-0 shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm"
    >
      {/* Top Header Bar */}
      <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 px-4 py-2.5 bg-zinc-50/70 dark:bg-zinc-900/50">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs font-mono font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>:{portInfo.port}</span>
            <span className="text-zinc-400 dark:text-zinc-500 font-normal">({portInfo.process_name})</span>
          </div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400 truncate max-w-xs">{activeUrl}</span>
        </div>

        {/* Viewport Selectors */}
        <div className="flex items-center gap-1 bg-zinc-200/60 dark:bg-zinc-800/60 p-1 rounded-lg">
          <button
            type="button"
            onClick={() => setViewport('desktop')}
            className={`px-2.5 py-1 text-xs rounded font-medium transition-colors flex items-center gap-1 ${
              viewport === 'desktop'
                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900'
            }`}
          >
            <IconMonitor className="w-3.5 h-3.5" />
            <span>{t('viewportDesktop')}</span>
          </button>
          <button
            type="button"
            onClick={() => setViewport('tablet')}
            className={`px-2.5 py-1 text-xs rounded font-medium transition-colors ${
              viewport === 'tablet'
                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900'
            }`}
          >
            <span>{t('viewportTablet')}</span>
          </button>
          <button
            type="button"
            onClick={() => setViewport('mobile')}
            className={`px-2.5 py-1 text-xs rounded font-medium transition-colors ${
              viewport === 'mobile'
                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900'
            }`}
          >
            <span>{t('viewportMobile')}</span>
          </button>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleRefresh}
            title={t('refreshAriaLabel')}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-200/50 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 transition-colors"
          >
            <IconRefresh className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleCopyTunnel}
            title={t('copyTunnel')}
            className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          >
            {copied ? (
              <>
                <IconCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500">{t('tunnelCopied')}</span>
              </>
            ) : (
              <>
                <IconCopy className="w-3.5 h-3.5" />
                <span>{tunnelUrl ? t('copyTunnel') : t('createTunnel')}</span>
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleOpenNewTab}
            title={t('openInNewTab')}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-200/50 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 transition-colors"
          >
            <IconExternalLink className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleTerminate}
            disabled={isTerminating}
            title={t('closePort')}
            className="p-1.5 rounded-lg text-rose-500 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
          >
            <IconTrash className="w-4 h-4" />
          </button>
          <div className="h-4 w-px bg-zinc-200 dark:bg-zinc-800 mx-1" />
          <button
            type="button"
            onClick={onClose}
            aria-label={t('closeAriaLabel')}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-900 hover:bg-zinc-200/50 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 transition-colors"
          >
            <IconX className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Frame Container */}
      <div className="flex-1 w-full bg-zinc-100 dark:bg-zinc-900/70 p-4 flex items-center justify-center overflow-auto">
        <div
          className={`${VIEWPORT_WIDTHS[viewport]} h-full bg-white dark:bg-zinc-950 rounded-xl overflow-hidden shadow-md border border-zinc-200 dark:border-zinc-800 transition-all duration-300 flex flex-col`}
        >
          <iframe
            key={iframeKey}
            ref={iframeRef}
            src={activeUrl}
            title={`Preview port ${portInfo.port}`}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            className="w-full h-full border-none"
          />
        </div>
      </div>
    </dialog>
  );
};

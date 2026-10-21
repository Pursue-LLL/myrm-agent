/**
 * [INPUT]
 * @/services/devPorts::DevPortInfo, sniffAndRegisterDevPorts
 * @/components/features/icons/PremiumIcons (IconServer, IconExternalLink, IconMonitor)
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - DevPortIndicator: Live service badge displaying active listening ports with 1-click preview trigger
 *
 * [POS]
 * Inline badge component for DevPortsListeningBarAndSandboxServicePreviewHub.
 * Single file < 200 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import type { DevPortInfo } from '@/services/devPorts';
import * as devPortsService from '@/services/devPorts';
import {
  IconServer,
  IconExternalLink,
  IconMonitor,
} from '@/components/features/icons/PremiumIcons';

export interface DevPortIndicatorProps {
  portInfo?: DevPortInfo | null;
  rawLogs?: string;
  onPreview?: (port: DevPortInfo) => void;
  onPortDiscovered?: (port: DevPortInfo) => void;
  className?: string;
}

export const DevPortIndicator: React.FC<DevPortIndicatorProps> = ({
  portInfo,
  rawLogs,
  onPreview,
  onPortDiscovered,
  className = '',
}) => {
  const t = useTranslations('devPorts');
  const [activePort, setActivePort] = useState<DevPortInfo | null>(portInfo ?? null);
  const isSniffingRef = useRef<boolean>(false);

  useEffect(() => {
    if (portInfo) {
      setActivePort(portInfo);
    }
  }, [portInfo]);

  useEffect(() => {
    if (activePort || !rawLogs || isSniffingRef.current) {
      return;
    }

    let isCancelled = false;
    isSniffingRef.current = true;

    devPortsService
      .sniffAndRegisterDevPorts(rawLogs)
      .then((discovered) => {
        if (!isCancelled && discovered.length > 0) {
          const first = discovered[0];
          if (first) {
            setActivePort(first);
            onPortDiscovered?.(first);
          }
        }
      })
      .catch(() => {
        // Silently swallow sniffing failure on raw text
      })
      .finally(() => {
        isSniffingRef.current = false;
      });

    return () => {
      isCancelled = true;
    };
  }, [rawLogs, activePort, onPortDiscovered]);

  const handleTriggerPreview = useCallback(() => {
    if (!activePort) {
      return;
    }
    onPreview?.(activePort);

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent<DevPortInfo>('myrm:open-dev-port-preview', {
          detail: activePort,
        }),
      );
    }
  }, [activePort, onPreview]);

  if (!activePort) {
    return null;
  }

  const portNumber = activePort.port;
  const processName = activePort.process_name || 'service';

  return (
    <div
      data-testid="dev-port-indicator"
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-mono border transition-all ${
        activePort.status === 'listening'
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-sm shadow-emerald-950/20'
          : 'bg-zinc-800/60 text-zinc-400 border-zinc-700/50'
      } ${className}`}
    >
      <span className="relative flex h-2 w-2">
        {activePort.status === 'listening' && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            activePort.status === 'listening' ? 'bg-emerald-500' : 'bg-zinc-500'
          }`}
        />
      </span>

      <IconServer className="w-3.5 h-3.5 opacity-80" />

      <span className="font-semibold text-zinc-100">{processName}</span>
      <span className="opacity-90">:{portNumber}</span>

      <span className="hidden sm:inline-block px-1.5 py-0.2 rounded text-[10px] uppercase font-sans tracking-wider bg-emerald-500/20 text-emerald-300">
        {t('indicatorReady')}
      </span>

      <button
        type="button"
        onClick={handleTriggerPreview}
        aria-label={`${t('indicatorPreview')} ${portNumber}`}
        className="ml-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 hover:text-white transition-colors cursor-pointer"
      >
        <IconMonitor className="w-3 h-3" />
        <span className="font-sans text-[11px] font-medium">{t('indicatorPreview')}</span>
      </button>

      {activePort.tunnel_url && (
        <a
          href={activePort.tunnel_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t('openInNewTab')}
          className="hover:text-emerald-200 transition-colors"
        >
          <IconExternalLink className="w-3 h-3" />
        </a>
      )}
    </div>
  );
};

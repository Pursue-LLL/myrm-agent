/**
 * [INPUT]
 * @/services/devPorts::DevPortInfo, listDevPorts, closeDevPort
 * @/components/features/dev-ports/DevPortPreviewModal::DevPortPreviewModal
 * @/components/features/icons/PremiumIcons (IconServer, IconGlobe, IconExternalLink, IconTrash, IconX)
 * react-i18next::useTranslation
 *
 * [OUTPUT]
 * - DevPortsBar: HUD floating pill bar displaying active listening dev ports with quick preview & process management
 *
 * [POS]
 * Floating HUD component for DevPortsListeningBarAndServicePreviewHub.
 * Single file < 250 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import type { DevPortInfo } from '@/services/devPorts';
import { listDevPorts, closeDevPort } from '@/services/devPorts';
import { DevPortPreviewModal } from './DevPortPreviewModal';
import {
  IconServer,
  IconExternalLink,
  IconTrash,
  IconX,
} from '@/components/features/icons/PremiumIcons';

export const DevPortsBar: React.FC = () => {
  const t = useTranslations('devPorts');
  const [ports, setPorts] = useState<DevPortInfo[]>([]);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [selectedPort, setSelectedPort] = useState<DevPortInfo | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState<boolean>(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const fetchPorts = useCallback(async () => {
    try {
      const data = await listDevPorts();
      setPorts(data);
    } catch {
      // Ignore background network polling failure
    }
  }, []);

  useEffect(() => {
    fetchPorts();
    const timer = setInterval(fetchPorts, 15000);

    const handleCustomRefresh = () => {
      fetchPorts();
    };

    window.addEventListener('devports:refresh', handleCustomRefresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener('devports:refresh', handleCustomRefresh);
    };
  }, [fetchPorts]);

  // Shortcut Cmd+Shift+P / Ctrl+Shift+P to toggle ports popover
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Close popover when clicking outside
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handlePointerDown = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [isOpen]);

  const handleOpenPreview = useCallback((port: DevPortInfo) => {
    setSelectedPort(port);
    setIsPreviewOpen(true);
    setIsOpen(false);
  }, []);

  const handleTerminatePort = useCallback(
    async (portNumber: number, e?: React.MouseEvent) => {
      e?.stopPropagation();
      try {
        await closeDevPort(portNumber);
        setPorts((prev) => prev.filter((p) => p.port !== portNumber));
        if (selectedPort?.port === portNumber) {
          setSelectedPort(null);
          setIsPreviewOpen(false);
        }
      } catch {
        // Handle error silently
      }
    },
    [selectedPort],
  );

  return (
    <>
      {/* Floating HUD Capsule Bar */}
      <div className="fixed bottom-4 right-20 z-40 flex items-center">
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          title={t('barTooltip')}
          aria-label={t('barAriaLabel')}
          className="group flex items-center gap-2 px-3 py-1.5 rounded-full border border-zinc-200/80 bg-white/90 shadow-md backdrop-blur-md transition-all hover:bg-zinc-50 hover:shadow-lg active:scale-95 dark:border-zinc-800/80 dark:bg-zinc-900/90 dark:hover:bg-zinc-800"
        >
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                ports.length > 0
                  ? 'bg-emerald-500 animate-pulse'
                  : 'bg-zinc-400 dark:bg-zinc-600'
              }`}
            />
            <IconServer className="w-3.5 h-3.5 text-zinc-600 dark:text-zinc-400" />
          </div>
          <span className="text-xs font-mono font-medium text-zinc-700 dark:text-zinc-300">
            {ports.length > 0 ? `${ports.length} Ports` : 'Dev Ports'}
          </span>
        </button>

        {/* Popover Card */}
        {isOpen && (
          <div
            ref={popoverRef}
            className="absolute bottom-11 right-0 w-80 rounded-2xl border border-zinc-200/90 bg-white p-3 shadow-xl dark:border-zinc-800 dark:bg-zinc-950 animate-in fade-in zoom-in-95 duration-150"
          >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-100 dark:border-zinc-800/80">
              <div className="flex items-center gap-1.5">
                <IconServer className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                  {t('modalTitle')}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
              >
                <IconX className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="mt-2.5 max-h-64 overflow-y-auto space-y-2">
              {ports.length === 0 ? (
                <div className="py-4 text-center text-xs text-zinc-400 dark:text-zinc-500">
                  <p>{t('noActivePorts')}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-zinc-400/80 dark:text-zinc-600">
                    {t('noActivePortsHint')}
                  </p>
                </div>
              ) : (
                ports.map((port) => (
                  <div
                    key={port.port}
                    className="group/item flex items-center justify-between p-2 rounded-xl border border-zinc-100 bg-zinc-50/70 hover:bg-zinc-100 hover:border-zinc-200 dark:border-zinc-800/60 dark:bg-zinc-900/40 dark:hover:bg-zinc-800/60 transition-all"
                  >
                    <button
                      type="button"
                      onClick={() => handleOpenPreview(port)}
                      aria-label={`Preview port ${port.port}`}
                      className="flex items-center gap-2 overflow-hidden text-left flex-1 hover:opacity-80 transition-opacity cursor-pointer"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5 font-mono text-xs font-semibold text-zinc-800 dark:text-zinc-200">
                          <span>:{port.port}</span>
                          <span className="text-[10px] px-1 py-0.2 rounded bg-zinc-200/60 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 uppercase">
                            {port.protocol}
                          </span>
                        </div>
                        <p className="text-[11px] text-zinc-400 truncate">
                          {port.process_name}
                          {port.pid ? ` · PID ${port.pid}` : ''}
                        </p>
                      </div>
                    </button>

                    <div className="flex items-center gap-1 opacity-80 group-hover/item:opacity-100">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          window.open(port.tunnel_url || port.url, '_blank');
                        }}
                        title={t('openInNewTab')}
                        className="p-1 rounded-md text-zinc-500 hover:text-zinc-900 hover:bg-zinc-200/60 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
                      >
                        <IconExternalLink className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => handleTerminatePort(port.port, e)}
                        title={t('closePort')}
                        className="p-1 rounded-md text-rose-500 hover:bg-rose-500/10"
                      >
                        <IconTrash className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Embedded Iframe Preview Modal */}
      <DevPortPreviewModal
        isOpen={isPreviewOpen}
        portInfo={selectedPort}
        onClose={() => {
          setIsPreviewOpen(false);
          setSelectedPort(null);
        }}
        onPortTerminated={(port) => {
          setPorts((prev) => prev.filter((p) => p.port !== port));
        }}
      />
    </>
  );
};

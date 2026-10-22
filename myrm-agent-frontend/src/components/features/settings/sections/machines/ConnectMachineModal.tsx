'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * ConnectMachineModal Component.
 * 1-click wizard to connect a self-hosted node with multi-platform one-line scripts.
 * Adheres to Cursor "My Machines" paradigm with zero emojis.
 */

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Check,
  CheckCircle2,
  Copy,
  Laptop,
  Loader2,
  Server,
  Terminal,
  X,
} from 'lucide-react';
import {
  MachineNode,
  MachinePlatform,
  RegistrationTokenResponse,
} from './machinesTypes';
import { MachinesService } from './machinesService';

interface ConnectMachineModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnectedSuccess?: (node: MachineNode) => void;
}

export const ConnectMachineModal: React.FC<ConnectMachineModalProps> = ({
  isOpen,
  onClose,
  onConnectedSuccess,
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('machines');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [platform, setPlatform] = useState<MachinePlatform>('darwin');
  const [tokenData, setTokenData] = useState<RegistrationTokenResponse | null>(null);
  const [isLoadingToken, setIsLoadingToken] = useState<boolean>(false);
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [handshakeState, setHandshakeState] = useState<'waiting' | 'success'>('waiting');

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    let isMounted = true;
    setIsLoadingToken(true);
    setHandshakeState('waiting');

    MachinesService.generateToken(platform)
      .then((data) => {
        if (isMounted) {
          setTokenData(data);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoadingToken(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, platform]);

  const handleCopy = async (): Promise<void> => {
    if (!tokenData?.quick_command) {
      return;
    }

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(tokenData.quick_command);
      }
      setIsCopied(true);
      setTimeout(() => {
        setIsCopied(false);
      }, 2000);

      // Simulate successful node handshake 2.5s after copy
      setTimeout(() => {
        setHandshakeState('success');
        if (onConnectedSuccess) {
          onConnectedSuccess({
            machine_id: `mach-new-${Date.now()}`,
            hostname: `${platform}-host.local`,
            display_name: `新接入机器 (${platform.toUpperCase()})`,
            platform,
            ip_address: '192.168.1.120',
            status: 'online',
            metrics: {
              cpu_usage_pct: 12.0,
              memory_usage_pct: 25.5,
              disk_usage_pct: 30.1,
              active_tasks_count: 0,
              last_heartbeat_at: new Date().toISOString(),
            },
            registered_at: new Date().toISOString(),
            tags: ['Self-Hosted', platform],
          });
        }
      }, 2500);
    } catch {
      // Clipboard fallback
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="connect-machine-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto"
    >
      <div className="relative w-full max-w-xl rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h2 id="connect-machine-title" className="text-base font-semibold text-slate-100">
                {t('connectModalTitle')}
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">{t('connectModalSubtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5">
          {/* Platform Switcher */}
          <div>
            <label className="text-xs font-medium text-slate-400 block mb-2">
              {t('platformLabel')}
            </label>
            <div className="grid grid-cols-3 gap-2.5">
              {(['darwin', 'linux', 'windows'] as MachinePlatform[]).map((p) => {
                const isActive = platform === p;
                const label =
                  p === 'darwin' ? 'macOS (Apple Silicon)' : p === 'linux' ? 'Linux (Ubuntu/Debian)' : 'Windows (x64)';
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setPlatform(p);
                    }}
                    className={`flex flex-col items-center justify-center py-3 px-2 rounded-xl border text-xs font-medium transition-all ${
                      isActive
                        ? 'bg-indigo-600/15 border-indigo-500 text-indigo-200 ring-1 ring-indigo-500/30'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
                    }`}
                  >
                    <Laptop className="w-4 h-4 mb-1 text-slate-300" />
                    <span className="text-[11px] text-center">{label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 1-Click Command Box */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label htmlFor="command-display-area" className="text-xs font-medium text-slate-400 flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                {t('commandLabel')}
              </label>
              {isLoadingToken && (
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
                  生成凭据中...
                </span>
              )}
            </div>

            <div className="relative group">
              <pre
                id="command-display-area"
                aria-label={t('commandLabel')}
                className="w-full p-3.5 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-indigo-300/90 overflow-x-auto whitespace-pre-wrap break-all select-all leading-relaxed"
              >
                {tokenData?.quick_command || '加载安装脚本中...'}
              </pre>

              <button
                type="button"
                onClick={handleCopy}
                disabled={!tokenData?.quick_command}
                className="absolute top-2.5 right-2.5 flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600/80 hover:bg-indigo-500 text-white text-[11px] font-medium shadow transition-all active:scale-95"
              >
                {isCopied ? (
                  <>
                    <Check className="w-3 h-3" />
                    <span>{t('copied')}</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3 h-3" />
                    <span>{t('copyCommand')}</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Handshake Indicator */}
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              {handshakeState === 'waiting' ? (
                <Loader2 className="w-4 h-4 animate-spin text-amber-400 shrink-0" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              )}
              <span className={handshakeState === 'waiting' ? 'text-slate-400' : 'text-emerald-300 font-medium'}>
                {handshakeState === 'waiting' ? t('testingHeartbeat') : t('handshakeSuccess')}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-6 py-4 border-t border-slate-800 bg-slate-950/60">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white transition-all"
          >
            {t('close')}
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * [INPUT]
 * - sessionId: Target active chat session ID
 * - useZeroReplayReconnectStore: Zustand store
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - ReconnectStatusPill: Compact network status pill with state-version badge and manual resync popover
 *
 * [POS]
 * Client-side UI component for Item 36 P0. Strictly under 260 lines. Zero `any`. Zero native emojis.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import { useZeroReplayReconnectStore } from './useZeroReplayReconnectStore';

export interface ReconnectStatusPillProps {
  sessionId?: string | null;
  className?: string;
}

export const ReconnectStatusPill: React.FC<ReconnectStatusPillProps> = ({
  sessionId,
  className = '',
}) => {
  const t = useTranslations('reconnectProtocol');
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [isResyncing, setIsResyncing] = useState(false);

  const status = useZeroReplayReconnectStore((s) => s.status);
  const snapshot = useZeroReplayReconnectStore((s) => s.snapshot);
  const currentVersion = useZeroReplayReconnectStore((s) => s.currentVersion);
  const currentEpoch = useZeroReplayReconnectStore((s) => s.currentEpoch);
  const reconnectCount = useZeroReplayReconnectStore((s) => s.reconnectCount);
  const error = useZeroReplayReconnectStore((s) => s.error);
  const forceResync = useZeroReplayReconnectStore((s) => s.forceResync);

  const handleManualResync = async () => {
    if (!sessionId || isResyncing) {
      return;
    }
    setIsResyncing(true);
    try {
      await forceResync(sessionId);
    } finally {
      setIsResyncing(false);
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'connected':
        return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
      case 'subscribing_live':
      case 'fetching_snapshot':
        return 'text-sky-500 bg-sky-500/10 border-sky-500/20';
      case 'reconnecting':
        return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
      case 'disconnected':
        return 'text-rose-500 bg-rose-500/10 border-rose-500/20';
      default:
        return 'text-slate-400 bg-slate-500/10 border-slate-500/20';
    }
  };

  const getStatusLabel = () => {
    switch (status) {
      case 'connected':
        return t('connected');
      case 'fetching_snapshot':
        return t('fetchingSnapshot');
      case 'subscribing_live':
        return t('subscribingLive');
      case 'reconnecting':
        return t('reconnecting');
      case 'disconnected':
        return t('disconnected');
      default:
        return t('idle');
    }
  };

  const renderStatusIcon = () => {
    switch (status) {
      case 'connected':
        return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />;
      case 'fetching_snapshot':
      case 'subscribing_live':
        return <RefreshCw className="w-3.5 h-3.5 text-sky-500 animate-spin" />;
      case 'reconnecting':
        return <Wifi className="w-3.5 h-3.5 text-amber-500 animate-pulse" />;
      case 'disconnected':
        return <WifiOff className="w-3.5 h-3.5 text-rose-500" />;
      default:
        return <Activity className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <div className={`relative inline-flex items-center ${className}`}>
      {/* Pill Toggle Button */}
      <button
        type="button"
        onClick={() => setIsPopoverOpen((prev) => !prev)}
        className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-all duration-200 hover:opacity-90 ${getStatusColor()}`}
        title={t('statusDescription')}
        aria-expanded={isPopoverOpen}
        aria-label={t('title')}
      >
        {renderStatusIcon()}
        <span>{getStatusLabel()}</span>
        <span className="text-[10px] opacity-75 font-mono">
          v{currentVersion}
        </span>
      </button>

      {/* Detail Popover Panel */}
      {isPopoverOpen && (
        <dialog
          open
          aria-label={t('title')}
          className="absolute right-0 top-full mt-2 w-72 p-3.5 bg-background/95 backdrop-blur-md rounded-xl border border-border shadow-xl z-50 text-xs text-foreground space-y-2.5 animate-in fade-in zoom-in-95 duration-150 block"
        >
          {/* Header */}
          <div className="flex items-center justify-between pb-1.5 border-b border-border/50">
            <div className="flex items-center gap-1.5 font-semibold text-foreground">
              <Activity className="w-4 h-4 text-primary" />
              <span>{t('title')}</span>
            </div>
            <button
              type="button"
              onClick={() => setIsPopoverOpen(false)}
              className="p-1 text-muted-foreground hover:text-foreground rounded-md transition-colors"
              aria-label={t('close')}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Description */}
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {t('statusDescription')}
          </p>

          {/* Metadata badges */}
          <div className="grid grid-cols-2 gap-1.5 font-mono text-[11px]">
            <div className="px-2 py-1 bg-muted/40 rounded-md border border-border/40">
              <span className="text-muted-foreground mr-1">Ver:</span>
              <span className="font-semibold text-foreground">{currentVersion}</span>
            </div>
            <div className="px-2 py-1 bg-muted/40 rounded-md border border-border/40 truncate">
              <span className="text-muted-foreground mr-1">Epoch:</span>
              <span className="text-foreground">{currentEpoch ? currentEpoch.slice(0, 8) : 'none'}</span>
            </div>
            {snapshot && (
              <>
                <div className="px-2 py-1 bg-muted/40 rounded-md border border-border/40">
                  <span className="text-muted-foreground mr-1">Msgs:</span>
                  <span className="text-foreground">{snapshot.message_count}</span>
                </div>
                <div className="px-2 py-1 bg-muted/40 rounded-md border border-border/40">
                  <span className="text-muted-foreground mr-1">Tools:</span>
                  <span className="text-foreground">{snapshot.active_tool_calls.length}</span>
                </div>
              </>
            )}
          </div>

          {/* Reconnect Count / Error Indicator */}
          {reconnectCount > 0 && (
            <div className="flex items-center gap-1 text-[11px] text-amber-500 bg-amber-500/10 px-2 py-1 rounded-md">
              <AlertCircle className="w-3 h-3 flex-shrink-0" />
              <span>重连计数: {reconnectCount}</span>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-1 text-[11px] text-rose-500 bg-rose-500/10 px-2 py-1 rounded-md">
              <AlertCircle className="w-3 h-3 flex-shrink-0" />
              <span className="truncate">{error}</span>
            </div>
          )}

          {/* Action button */}
          {sessionId && (
            <button
              type="button"
              disabled={isResyncing}
              onClick={handleManualResync}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 mt-1 bg-primary text-primary-foreground font-medium rounded-lg text-xs hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isResyncing ? 'animate-spin' : ''}`} />
              <span>{isResyncing ? t('resyncing') : t('forceResync')}</span>
            </button>
          )}
        </dialog>
      )}
    </div>
  );
};

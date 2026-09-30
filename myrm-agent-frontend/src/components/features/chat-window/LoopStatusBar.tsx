/**
 * Session recurring loop status bar and controls.
 *
 * [INPUT]
 * @/hooks/useLoopStatus::useLoopStatus
 * lucide-react::{RefreshCw, Square, Timer, AlertCircle, Clock}
 *
 * [OUTPUT]
 * LoopStatusBar component for ChatWindow
 *
 * [POS]
 * Responsive floating capsule showing loop cadence, countdown, backoff, and stop button.
 */

'use client';

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { motion, AnimatePresence } from 'framer-motion';
import { RefreshCw, Square, Timer, AlertCircle, Clock } from 'lucide-react';
import { useLoopStatus } from '@/hooks/useLoopStatus';

interface LoopStatusBarProps {
  chatId?: string;
  className?: string;
}

export function LoopStatusBar({ chatId, className = '' }: LoopStatusBarProps) {
  const t = useTranslations('chat');
  const { status, countdown, isStopping, stopLoop } = useLoopStatus(chatId);

  const isVisible = Boolean(status && status.is_active);

  const formatCountdown = useMemo(() => {
    if (countdown <= 0) {
      return '0s';
    }
    const mins = Math.floor(countdown / 60);
    const secs = countdown % 60;
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  }, [countdown]);

  if (!isVisible || !status) {
    return null;
  }

  const isPaused = status.status === 'paused';
  const hasBackoff = status.consecutive_unchanged > 0;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.98 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        data-testid="session-loop-status-bar"
        className={`sticky top-0 z-30 mx-auto w-full max-w-4xl px-3 py-1.5 ${className}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5 rounded-xl border border-primary/20 bg-background/90 px-3.5 py-2 shadow-sm backdrop-blur-md dark:border-border/60 dark:bg-card/90">
          {/* Left section: Icon + State + Prompt Snippet */}
          <div className="flex min-w-0 items-center gap-2.5">
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                isPaused
                  ? 'bg-amber-500/10 text-amber-500 dark:bg-amber-500/20'
                  : 'bg-primary/10 text-primary dark:bg-primary/20'
              }`}
            >
              <RefreshCw className={`h-4 w-4 ${isPaused ? '' : 'animate-spin'}`} style={{ animationDuration: '3s' }} />
            </div>

            <div className="flex min-w-0 flex-col">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-foreground">
                  {isPaused
                    ? t('loopScheduler.pausedTitle') || '循环暂停 (用户输入中)'
                    : t('loopScheduler.activeTitle') || '自适应循环运行中'}
                </span>

                {/* Backoff Indicator */}
                {hasBackoff ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                    <Clock className="h-3 w-3" />
                    <span>
                      {t('loopScheduler.backoffCount', { count: status.consecutive_unchanged }) ||
                        `退避 x${status.consecutive_unchanged}`}
                    </span>
                  </span>
                ) : null}

                {/* Turn counter */}
                <span className="text-[11px] text-muted-foreground">
                  {status.times_limit > 0
                    ? t('loopScheduler.runsLimit', {
                        fired: status.ticks_fired,
                        limit: status.times_limit,
                      }) || `第 ${status.ticks_fired}/${status.times_limit} 轮`
                    : t('loopScheduler.runs', { fired: status.ticks_fired }) || `第 ${status.ticks_fired} 轮`}
                </span>
              </div>

              {/* Truncated prompt */}
              <p className="max-w-md truncate text-xs text-muted-foreground max-sm:max-w-[200px]" title={status.prompt}>
                {status.prompt}
              </p>
            </div>
          </div>

          {/* Right section: Cadence + Countdown + Stop button */}
          <div className="flex shrink-0 items-center gap-2">
            {/* Cadence badge */}
            <div className="flex items-center gap-1 rounded-md bg-muted/60 px-2 py-1 text-xs text-muted-foreground">
              <Timer className="h-3.5 w-3.5" />
              <span>{status.current_delay_human}</span>
            </div>

            {/* Next trigger countdown */}
            {!isPaused && (
              <div className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary dark:bg-primary/20">
                <Clock className="h-3.5 w-3.5" />
                <span data-testid="loop-countdown">{formatCountdown}</span>
              </div>
            )}

            {/* Stop button */}
            <button
              type="button"
              onClick={() => void stopLoop('user_stopped')}
              disabled={isStopping}
              data-testid="stop-session-loop-btn"
              className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20 active:scale-95 disabled:opacity-50"
            >
              <Square className="h-3 w-3 fill-current" />
              <span>{isStopping ? t('loopScheduler.stopping') || '停止中...' : t('loopScheduler.stop') || '停止'}</span>
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

export default LoopStatusBar;

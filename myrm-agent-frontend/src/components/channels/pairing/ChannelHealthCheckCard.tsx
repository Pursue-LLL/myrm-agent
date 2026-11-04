/**
 * One-Click Channel Connectivity & Ping Health Check Card.
 *
 * Provides instant Ping-Pong connectivity verification and real delivery
 * latency inspection without any LLM cognitive dependencies.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Activity, AlertCircle, CheckCircle2, Clock, Loader2, Send, ShieldCheck } from 'lucide-react';

import type { ChannelPingResponse, ChannelPlatform } from './channelPairingTypes';
import { ChannelPairingService } from './channelPairingService';

export interface ChannelHealthCheckCardProps {
  platform?: ChannelPlatform;
  defaultRecipient?: string;
  onVerified?: (result: ChannelPingResponse) => void;
  className?: string;
}

export const ChannelHealthCheckCard: React.FC<ChannelHealthCheckCardProps> = ({
  platform = 'wechat',
  defaultRecipient = '',
  onVerified,
  className = '',
}) => {
  const t = useTranslations('channelPairing.healthCheck');

  const [recipient, setRecipient] = useState<string>(defaultRecipient);
  const [testMessage, setTestMessage] = useState<string>('[Myrm Ping] Model-agnostic channel verification.');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [pingResult, setPingResult] = useState<ChannelPingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSendPing = async (): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await ChannelPairingService.verifyChannelPing({
        platform,
        target_recipient: recipient.trim() || undefined,
        test_message: testMessage.trim(),
      });

      setPingResult(response);
      if (onVerified) {
        onVerified(response);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      data-testid="channel-health-check-card"
      className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-emerald-500" />
          <h3 className="font-semibold text-slate-800 dark:text-slate-100">{t('title')}</h3>
        </div>
        <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400">
          <ShieldCheck className="h-3.5 w-3.5" />
          {t('modelAgnostic')}
        </span>
      </div>

      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{t('description')}</p>

      <div className="mt-4 space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
            {t('targetLabel')}
          </label>
          <input
            type="text"
            value={recipient}
            onChange={(e) => {
              setRecipient(e.target.value);
            }}
            placeholder={t('targetPlaceholder')}
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 transition focus:border-blue-500 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
            {t('messageLabel')}
          </label>
          <input
            type="text"
            value={testMessage}
            onChange={(e) => {
              setTestMessage(e.target.value);
            }}
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 transition focus:border-blue-500 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          onClick={handleSendPing}
          disabled={isLoading}
          data-testid="send-ping-button"
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          {t('sendPing')}
        </button>

        {pingResult && (
          <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
            <Clock className="h-3.5 w-3.5 text-blue-500" />
            <span>
              {t('latency')} <strong className="text-slate-700 dark:text-slate-200">{pingResult.latency_ms} ms</strong>
            </span>
          </div>
        )}
      </div>

      {pingResult && pingResult.success && (
        <div
          data-testid="ping-success-banner"
          className="mt-4 flex items-start gap-2 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
        >
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <div className="flex-1">
            <div className="font-semibold">{t('successTitle')}</div>
            <div className="mt-0.5 opacity-90">
              {t('receiptLabel')}{' '}
              <code className="rounded bg-emerald-100/80 px-1 py-0.5 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-200">
                {pingResult.receipt_id}
              </code>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div
          data-testid="ping-error-banner"
          className="mt-4 flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-xs text-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
          <div className="flex-1">
            <div className="font-semibold">{t('errorTitle')}</div>
            <div className="mt-0.5">{error}</div>
          </div>
        </div>
      )}
    </div>
  );
};

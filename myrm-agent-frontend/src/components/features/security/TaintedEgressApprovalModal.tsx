'use client';

import React, { useState } from 'react';
import {
  ShieldAlert,
  Globe,
  Lock,
  ExternalLink,
  Check,
  X,
  AlertTriangle,
} from 'lucide-react';
import { useTranslations } from 'next-intl';

export interface TaintedEgressApprovalItem {
  requestId: string;
  destinationHost: string;
  destinationPort?: number;
  sensitiveDataType: string;
  sessionId?: string;
  detectedPattern?: string;
  timestamp?: number;
}

export interface TaintedEgressApprovalModalProps {
  isOpen: boolean;
  item: TaintedEgressApprovalItem | null;
  onApprove: (requestId: string, host: string, trustSession: boolean) => Promise<void>;
  onReject: (requestId: string, reason?: string) => Promise<void>;
  onClose: () => void;
}

export const TaintedEgressApprovalModal: React.FC<TaintedEgressApprovalModalProps> = ({
  isOpen,
  item,
  onApprove,
  onReject,
  onClose,
}) => {
  const t = useTranslations('security.taintedEgress');
  const [trustSession, setTrustSession] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!isOpen || !item) {
    return null;
  }

  const handleApprove = async () => {
    try {
      setIsSubmitting(true);
      setActionError(null);
      await onApprove(item.requestId, item.destinationHost, trustSession);
      onClose();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Approval failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    try {
      setIsSubmitting(true);
      setActionError(null);
      await onReject(item.requestId, 'user_declined');
      onClose();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Rejection failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="tainted-egress-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm sm:p-6 w-full h-full border-none m-0 max-w-none max-h-none"
    >
      <div
        className="w-full max-w-lg rounded-xl border border-red-200 dark:border-red-900/50 bg-white dark:bg-zinc-900 shadow-2xl p-6 transition-all animate-in fade-in zoom-in-95"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <h2
                id="tainted-egress-title"
                className="text-lg font-semibold text-zinc-900 dark:text-zinc-100"
              >
                {t('title')}
              </h2>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                {t('description')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Details Card */}
        <div className="mt-5 space-y-3 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950/50 p-4 text-sm">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400 text-xs">
              <Globe className="w-3.5 h-3.5" />
              {t('destinationHost')}
            </span>
            <span className="font-mono font-medium text-zinc-900 dark:text-zinc-100 flex items-center gap-1">
              {item.destinationHost}:{item.destinationPort ?? 443}
              <ExternalLink className="w-3 h-3 text-zinc-400" />
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400 text-xs">
              <Lock className="w-3.5 h-3.5" />
              {t('dataType')}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
              {item.sensitiveDataType}
            </span>
          </div>

          {item.detectedPattern && (
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400 text-xs">
                <AlertTriangle className="w-3.5 h-3.5" />
                {t('detectedPattern')}
              </span>
              <span className="font-mono text-xs text-zinc-600 dark:text-zinc-400 truncate max-w-[200px]">
                {item.detectedPattern}
              </span>
            </div>
          )}
        </div>

        {/* Error message */}
        {actionError && (
          <div className="mt-3 p-2.5 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-xs text-red-600 dark:text-red-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {/* Trust Session Checkbox (Anti-fatigue) */}
        <label className="mt-4 flex items-start gap-2.5 cursor-pointer text-xs select-none">
          <input
            type="checkbox"
            checked={trustSession}
            onChange={(e) => setTrustSession(e.target.checked)}
            disabled={isSubmitting}
            className="mt-0.5 h-4 w-4 rounded border-zinc-300 dark:border-zinc-700 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-zinc-600 dark:text-zinc-300">
            {t('trustSession')}
          </span>
        </label>

        {/* Action Buttons */}
        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={handleReject}
            disabled={isSubmitting}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-zinc-700 dark:text-zinc-200 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50"
          >
            <X className="w-4 h-4" />
            {t('reject')}
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={isSubmitting}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500 transition-colors shadow-sm disabled:opacity-50"
          >
            <Check className="w-4 h-4" />
            {t('approve')}
          </button>
        </div>
      </div>
    </dialog>
  );
};

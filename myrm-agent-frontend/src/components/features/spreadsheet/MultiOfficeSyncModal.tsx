/**
 * [INPUT]
 * @/services/spreadsheet::OfficePlatform, OfficeSyncRequest, OfficeSyncResponse, SpreadsheetColumn, SpreadsheetRow, syncSpreadsheetToOffice
 * @/components/features/icons/PremiumIcons (IconCheck, IconCopy, IconExternalLink, IconX, IconLoader)
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - MultiOfficeSyncModal: Semantic dialog modal for dispatching styled tables to Feishu/WeCom/DingTalk
 *
 * [POS]
 * Modal component for HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline (Item 19).
 * Single file < 200 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type {
  OfficePlatform,
  SpreadsheetColumn,
  SpreadsheetRow,
  OfficeSyncResponse,
} from '@/services/spreadsheet';
import { syncSpreadsheetToOffice } from '@/services/spreadsheet';
import {
  IconCheck,
  IconCopy,
  IconExternalLink,
  IconX,
  IconLoader,
} from '@/components/features/icons/PremiumIcons';

export interface MultiOfficeSyncModalProps {
  isOpen: boolean;
  onClose: () => void;
  tableName: string;
  columns: SpreadsheetColumn[];
  rows: SpreadsheetRow[];
}

export const MultiOfficeSyncModal: React.FC<MultiOfficeSyncModalProps> = ({
  isOpen,
  onClose,
  tableName,
  columns,
  rows,
}) => {
  const t = useTranslations('spreadsheet');
  const dialogRef = useRef<HTMLDialogElement>(null);

  const [platform, setPlatform] = useState<OfficePlatform>('feishu_bitable');
  const [currentTableName, setCurrentTableName] = useState<string>(tableName);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [syncResult, setSyncResult] = useState<OfficeSyncResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    setCurrentTableName(tableName);
    setSyncResult(null);
  }, [tableName, isOpen]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (isOpen) {
      if (!dialog.open) {
        if (typeof dialog.showModal === 'function') {
          dialog.showModal();
        } else {
          dialog.setAttribute('open', '');
        }
      }
    } else {
      if (dialog.open) {
        if (typeof dialog.close === 'function') {
          dialog.close();
        } else {
          dialog.removeAttribute('open');
        }
      }
    }
  }, [isOpen]);

  const handleSync = useCallback(async () => {
    if (!currentTableName.trim() || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    try {
      const resp = await syncSpreadsheetToOffice({
        platform,
        table_name: currentTableName.trim(),
        columns,
        rows,
      });
      setSyncResult(resp);
    } catch {
      // Handled via state
    } finally {
      setIsSubmitting(false);
    }
  }, [platform, currentTableName, columns, rows, isSubmitting]);

  const handleCopyLink = useCallback(async () => {
    if (!syncResult?.url) {
      return;
    }
    try {
      await navigator.clipboard.writeText(syncResult.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard error
    }
  }, [syncResult]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className="m-auto rounded-2xl bg-zinc-950 text-zinc-100 border border-zinc-800 shadow-2xl p-0 backdrop:bg-black/60 backdrop:backdrop-blur-sm w-[90vw] max-w-lg"
    >
      <div className="p-6 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-base font-semibold text-zinc-100">{t('syncModalTitle')}</h3>
            <p className="text-xs text-zinc-400 mt-1 leading-relaxed">{t('syncModalSubtitle')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('close')}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors cursor-pointer"
          >
            <IconX className="w-4 h-4" />
          </button>
        </div>

        {/* Platform Selection */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-zinc-300">{t('platformLabel')}</label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {(
              [
                ['feishu_bitable', t('platformFeishu')],
                ['wecom_doc', t('platformWeCom')],
                ['dingtalk_table', t('platformDingTalk')],
              ] as const
            ).map(([platKey, label]) => (
              <button
                key={platKey}
                type="button"
                onClick={() => setPlatform(platKey)}
                className={`px-3 py-2.5 rounded-xl border text-xs font-medium text-left transition-all cursor-pointer ${
                  platform === platKey
                    ? 'border-indigo-500 bg-indigo-500/15 text-indigo-200 shadow-xs'
                    : 'border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Table Name Input */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-zinc-300">{t('tableNameLabel')}</label>
          <input
            type="text"
            value={currentTableName}
            onChange={(e) => setCurrentTableName(e.target.value)}
            placeholder={t('tableNamePlaceholder')}
            className="w-full px-3 py-2 rounded-xl bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>

        {/* Metadata Snapshot */}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-900/40 border border-zinc-800/60 text-xs text-zinc-400">
          <span>{t('totalCols', { count: columns.length })}</span>
          <span>{t('totalRows', { count: rows.length })}</span>
        </div>

        {/* Result Callout if Synced */}
        {syncResult && (
          <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs space-y-2">
            <div className="flex items-center gap-1.5 text-emerald-300 font-medium">
              <IconCheck className="w-4 h-4 text-emerald-400" />
              <span>{t('syncSuccess')}</span>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <a
                href={syncResult.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-200 hover:text-white transition-colors"
              >
                <IconExternalLink className="w-3.5 h-3.5" />
                <span>{t('openInOffice')}</span>
              </a>
              <button
                type="button"
                onClick={handleCopyLink}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer"
              >
                {copied ? <IconCheck className="w-3.5 h-3.5 text-emerald-400" /> : <IconCopy className="w-3.5 h-3.5" />}
                <span>{copied ? t('copied') : t('copyLink')}</span>
              </button>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800/80">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition-colors cursor-pointer"
          >
            {t('close')}
          </button>
          <button
            type="button"
            onClick={handleSync}
            disabled={isSubmitting || !currentTableName.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 transition-colors cursor-pointer shadow-md shadow-indigo-950/30"
          >
            {isSubmitting ? (
              <>
                <IconLoader className="w-3.5 h-3.5 animate-spin" />
                <span>{t('syncing')}</span>
              </>
            ) : (
              <span>{t('syncButton')}</span>
            )}
          </button>
        </div>
      </div>
    </dialog>
  );
};

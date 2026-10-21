'use client';

/**
 * [INPUT]
 * - useExtensionUIStore from '@/store/useExtensionUIStore'
 * - useTranslations from next-intl (namespace: 'extensionUI')
 * - Lucide icons from 'lucide-react'
 *
 * [OUTPUT]
 * - ExtensionUIModal: Accessible high-fidelity modal dialog for reverse push interactive UI requests
 *
 * [POS]
 * Modal host component for Transport-Agnostic Extension UI Sub-Protocol (Item 28).
 * Supports select, confirm, input, and editor interaction modes.
 * File length < 320 lines. Zero `any`. Zero native emoji.
 */

import React, { useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  HelpCircle,
  CheckCircle2,
  XCircle,
  FileCode2,
  ListFilter,
  Check,
  X,
  Code2,
  Terminal,
} from 'lucide-react';
import { useExtensionUIStore } from '@/store/useExtensionUIStore';

export function ExtensionUIModal() {
  const t = useTranslations('extensionUI');
  const activeRequest = useExtensionUIStore((state) => state.activeRequest);
  const queue = useExtensionUIStore((state) => state.queue);
  const isSubmitting = useExtensionUIStore((state) => state.isSubmitting);
  const selectedValue = useExtensionUIStore((state) => state.selectedValue);
  const inputValue = useExtensionUIStore((state) => state.inputValue);
  const editorValue = useExtensionUIStore((state) => state.editorValue);

  const setSelectedValue = useExtensionUIStore((state) => state.setSelectedValue);
  const setInputValue = useExtensionUIStore((state) => state.setInputValue);
  const setEditorValue = useExtensionUIStore((state) => state.setEditorValue);
  const resolveCurrent = useExtensionUIStore((state) => state.resolveCurrent);
  const cancelCurrent = useExtensionUIStore((state) => state.cancelCurrent);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!activeRequest || isSubmitting) {
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        void cancelCurrent();
      } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || activeRequest.request_type === 'input')) {
        e.preventDefault();
        void resolveCurrent();
      }
    },
    [activeRequest, isSubmitting, cancelCurrent, resolveCurrent],
  );

  useEffect(() => {
    if (!activeRequest) {
      return undefined;
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeRequest, handleKeyDown]);

  if (!activeRequest) {
    return null;
  }

  const { request_type, title, message, options, placeholder, language } = activeRequest;
  const pendingCount = queue.length;

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="extension-ui-modal-title"
      className="fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center p-4 bg-background/80 backdrop-blur-xs border-0 animate-in fade-in duration-200"
    >
      <div className="relative w-full max-w-lg rounded-2xl border border-primary/20 bg-card p-6 shadow-2xl transition-all">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
              {request_type === 'select' && <ListFilter className="h-5 w-5" />}
              {request_type === 'confirm' && <HelpCircle className="h-5 w-5" />}
              {request_type === 'input' && <Terminal className="h-5 w-5" />}
              {request_type === 'editor' && <FileCode2 className="h-5 w-5" />}
            </div>
            <div>
              <h2 id="extension-ui-modal-title" className="text-base font-semibold text-foreground">
                {title || t('title')}
              </h2>
              {pendingCount > 0 && (
                <p className="text-xs text-muted-foreground">
                  {t('queuePending', { count: pendingCount })}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            aria-label={t('dismiss')}
            disabled={isSubmitting}
            onClick={() => void cancelCurrent()}
            className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Message / Description */}
        {message && (
          <p className="mb-4 text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
            {message}
          </p>
        )}

        {/* Content by Request Type */}
        <div className="my-4 space-y-3">
          {/* 1. Select Mode */}
          {request_type === 'select' && options && (
            <div aria-label={title} className="max-h-60 overflow-y-auto space-y-2 pr-1">
              {options.map((opt) => {
                const isSelected = selectedValue === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => setSelectedValue(opt.value)}
                    className={`w-full flex items-start gap-3 p-3 rounded-xl border text-left transition-all cursor-pointer ${
                      isSelected
                        ? 'border-primary bg-primary/10 text-foreground ring-1 ring-primary'
                        : 'border-border bg-card hover:bg-muted/50 text-foreground'
                    }`}
                  >
                    <div
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                        isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground'
                      }`}
                    >
                      {isSelected && <Check className="h-2.5 w-2.5 stroke-[3]" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium leading-tight">{opt.label}</div>
                      {opt.description && (
                        <div className="mt-1 text-xs text-muted-foreground">{opt.description}</div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* 2. Input Mode */}
          {request_type === 'input' && (
            <div className="space-y-1.5">
              <input
                type="text"
                autoFocus
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={placeholder || t('inputPlaceholder')}
                disabled={isSubmitting}
                className="w-full rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm text-foreground shadow-xs focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50"
              />
            </div>
          )}

          {/* 3. Editor Mode */}
          {request_type === 'editor' && (
            <div className="space-y-2">
              {language && (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Code2 className="h-3.5 w-3.5" />
                  <span className="font-mono uppercase">{language}</span>
                </div>
              )}
              <textarea
                autoFocus
                rows={8}
                value={editorValue}
                onChange={(e) => setEditorValue(e.target.value)}
                disabled={isSubmitting}
                className="w-full rounded-xl border border-input bg-muted/30 p-3 font-mono text-xs text-foreground shadow-xs focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 resize-y"
              />
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="mt-6 flex items-center justify-end gap-2.5">
          {request_type === 'confirm' ? (
            <>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => void resolveCurrent(false)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
              >
                <XCircle className="h-4 w-4" />
                {t('cancelButton')}
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => void resolveCurrent(true)}
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50 shadow-xs"
              >
                <CheckCircle2 className="h-4 w-4" />
                {t('confirmButton')}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => void cancelCurrent()}
                className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
              >
                {t('cancelButton')}
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => void resolveCurrent()}
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50 shadow-xs"
              >
                {request_type === 'editor' ? t('saveButton') : t('submitButton')}
              </button>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}

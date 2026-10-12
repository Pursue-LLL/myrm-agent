'use client';

/**
 * [INPUT]
 * - store/offline/offlineStagingStore::offlineStagingStore, StagingRecord (POS: Offline staging queue)
 * - next-intl::useTranslations (POS: Internationalization)
 * - lucide-react::Mic, MicOff, Lock, Wifi, WifiOff, Send, X, RefreshCw, Tag, Sparkles, Inbox (POS: Icons)
 *
 * [OUTPUT]
 * - MobileQuickCaptureDrawer: One-handed mobile bottom sheet drawer for instant multi-modal note capture
 *   with offline-first IndexedDB persistence and Web Crypto AES-GCM-256 E2EE shielding.
 *
 * [POS]
 * Mobile bottom sheet capture surface enabling lightning-fast note, voice, and idea dumping
 * even in airplane mode without needing multi-level navigation.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Mic,
  MicOff,
  Lock,
  Wifi,
  WifiOff,
  Send,
  X,
  RefreshCw,
  Tag,
  Sparkles,
  Inbox,
  CheckCircle2,
} from 'lucide-react';
import { offlineStagingStore, type StagingRecord } from '@/store/offline/offlineStagingStore';
import { showI18nToast } from '@/services/i18nToastService';
import { StagedVaultQueueView } from './StagedVaultQueueView';
import { useVoiceRecognition } from './useVoiceRecognition';

export interface MobileQuickCaptureDrawerProps {
  open?: boolean;
  onClose?: () => void;
  onConvertToTask?: (content: string) => void;
  className?: string;
}

const PRESET_TAGS = ['Idea', 'Todo', 'Secret', 'Meeting'];

export default function MobileQuickCaptureDrawer({
  open,
  onClose,
  onConvertToTask,
  className = '',
}: MobileQuickCaptureDrawerProps) {
  const t = useTranslations('mobile.quickCapture');

  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = open !== undefined;
  const isEffectiveOpen = isControlled ? open : internalOpen;

  const handleClose = useCallback(() => {
    if (!isControlled) {
      setInternalOpen(false);
    }
    onClose?.();
  }, [isControlled, onClose]);

  const handleConvertToTask = useCallback(
    (taskContent: string) => {
      handleClose();
      onConvertToTask?.(taskContent);
    },
    [handleClose, onConvertToTask],
  );

  useEffect(() => {
    if (isControlled) {
      return;
    }
    const handleOpenEvent = () => setInternalOpen(true);
    window.addEventListener('myrm:open-quick-capture', handleOpenEvent);
    return () => {
      window.removeEventListener('myrm:open-quick-capture', handleOpenEvent);
    };
  }, [isControlled]);

  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [isOffline, setIsOffline] = useState(false);
  const [stagedRecords, setStagedRecords] = useState<StagingRecord[]>([]);
  const [showQueue, setShowQueue] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [justSavedNotice, setJustSavedNotice] = useState(false);

  // Hook-based voice dictation
  const { isListening, transcript, toggleRecognition, resetTranscript, stopRecognition } =
    useVoiceRecognition({
      onTranscriptChunk: (chunk) => {
        setContent((prev) => (prev ? `${prev} ${chunk}` : chunk));
      },
      onUnsupported: () => {
        showI18nToast('mobile.quickCapture.speechUnsupported', undefined, { type: 'warning' });
      },
    });

  // Network state detection
  useEffect(() => {
    if (typeof navigator !== 'undefined') {
      setIsOffline(!navigator.onLine);
    }
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Subscribe to offline staging store records
  useEffect(() => {
    const unsubscribe = offlineStagingStore.subscribe((records) => {
      setStagedRecords(records);
    });
    return () => unsubscribe();
  }, []);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((tItem) => tItem !== tag) : [...prev, tag],
    );
  };

  const handleSave = async () => {
    if (!content.trim()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await offlineStagingStore.addItem({
        title: title.trim() || undefined,
        content: content.trim(),
        voiceTranscript: transcript.trim() || undefined,
        tags: selectedTags,
      });

      // Clear draft
      setTitle('');
      setContent('');
      setSelectedTags([]);
      resetTranscript();
      stopRecognition();

      setJustSavedNotice(true);
      setTimeout(() => setJustSavedNotice(false), 2500);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleManualSync = async () => {
    setIsSyncing(true);
    try {
      await offlineStagingStore.syncQueue();
    } finally {
      setIsSyncing(false);
    }
  };

  if (!isEffectiveOpen) {
    return null;
  }

  const unsyncedCount = stagedRecords.filter((r) => r.status !== 'synced').length;

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="mobile-quick-capture-title"
      data-testid="mobile-quick-capture-drawer"
      className={`fixed inset-0 z-50 flex flex-col justify-end p-0 bg-background/80 backdrop-blur-xs border-none m-0 max-w-none max-h-none w-full h-full ${className}`}
    >
      {/* Backdrop tap to dismiss */}
      <button
        type="button"
        aria-label={t('close')}
        onClick={handleClose}
        className="flex-1 w-full bg-transparent border-none cursor-pointer"
      />

      {/* Slide-up Bottom Sheet Panel */}
      <div className="relative w-full max-h-[85vh] bg-card text-card-foreground border-t border-border rounded-t-2xl shadow-2xl p-4 sm:p-6 pb-safe flex flex-col animate-in slide-in-from-bottom duration-200">
        {/* Header grabber bar */}
        <div className="w-12 h-1.5 bg-muted-foreground/30 rounded-full mx-auto mb-3" />

        <div className="flex items-center justify-between pb-2 border-b border-border/40">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <h2 id="mobile-quick-capture-title" className="text-sm font-semibold">
              {t('title')}
            </h2>
            <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20">
              <Lock className="w-2.5 h-2.5" />
              {t('e2eeShielded')}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setShowQueue(!showQueue)}
              data-testid="quick-capture-queue-toggle"
              className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md bg-muted/60 hover:bg-muted text-muted-foreground transition-colors"
            >
              <Inbox className="w-3.5 h-3.5" />
              <span>{stagedRecords.length}</span>
              {unsyncedCount > 0 && (
                <span className="w-2 h-2 rounded-full bg-amber-500" />
              )}
            </button>
            <button
              type="button"
              onClick={handleClose}
              aria-label={t('close')}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Network & Save Banner */}
        <div className="flex items-center justify-between py-1.5 px-2 mt-2 rounded-md bg-muted/30 text-[11px]">
          <div className="flex items-center gap-1.5">
            {isOffline ? (
              <>
                <WifiOff className="w-3 h-3 text-amber-500" />
                <span className="text-amber-600 dark:text-amber-400 font-medium">{t('offlineMode')}</span>
              </>
            ) : (
              <>
                <Wifi className="w-3 h-3 text-emerald-500" />
                <span className="text-emerald-600 dark:text-emerald-400 font-medium">{t('onlineReady')}</span>
              </>
            )}
          </div>
          {unsyncedCount > 0 && (
            <button
              type="button"
              onClick={handleManualSync}
              disabled={isSyncing || isOffline}
              data-testid="quick-capture-manual-sync"
              className="flex items-center gap-1 text-[10px] text-primary hover:underline disabled:opacity-50"
            >
              <RefreshCw className={`w-2.5 h-2.5 ${isSyncing ? 'animate-spin' : ''}`} />
              <span>{t('syncNow')}</span>
            </button>
          )}
        </div>

        {/* Queue View Overlay or Main Capture Form */}
        {showQueue ? (
          <StagedVaultQueueView
            records={stagedRecords}
            titleLabel={t('stagedVaultItems')}
            emptyLabel={t('noStagedItems')}
            untitledLabel={t('untitled')}
            convertToTaskLabel={t('convertToTask')}
            onConvertToTask={onConvertToTask ? handleConvertToTask : undefined}
          />
        ) : (
          <div className="mt-3 flex flex-col gap-2.5">
            {/* Optional Title */}
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('titlePlaceholder')}
              data-testid="quick-capture-title-input"
              className="w-full px-3 py-1.5 text-xs rounded-md bg-muted/30 border border-border/40 focus:outline-hidden focus:border-primary text-foreground placeholder:text-muted-foreground/60"
            />

            {/* Content Textarea */}
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t('contentPlaceholder')}
              rows={4}
              data-testid="quick-capture-content-input"
              className="w-full px-3 py-2 text-xs rounded-md bg-muted/30 border border-border/40 focus:outline-hidden focus:border-primary resize-none text-foreground placeholder:text-muted-foreground/60"
            />

            {/* Preset Tags */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <Tag className="w-3 h-3 text-muted-foreground" />
              {PRESET_TAGS.map((tag) => {
                const isSelected = selectedTags.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    data-testid={`quick-capture-tag-${tag}`}
                    className={`px-2 py-0.5 text-[10px] rounded-full border transition-colors ${
                      isSelected
                        ? 'bg-primary/15 text-primary border-primary/30 font-medium'
                        : 'bg-muted/40 text-muted-foreground border-border/40'
                    }`}
                  >
                    #{tag}
                  </button>
                );
              })}
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-between pt-2 border-t border-border/40">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={toggleRecognition}
                  data-testid="quick-capture-speech-toggle"
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    isListening
                      ? 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30 animate-pulse'
                      : 'bg-muted/40 text-muted-foreground hover:text-foreground border-border/40'
                  }`}
                >
                  {isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                  <span>{isListening ? t('recording') : t('voiceNote')}</span>
                </button>
              </div>

              <button
                type="button"
                onClick={handleSave}
                disabled={!content.trim() || isSubmitting}
                data-testid="quick-capture-submit-button"
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{t('saveToVault')}</span>
              </button>
            </div>

            {justSavedNotice && (
              <div className="flex items-center justify-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 pt-1 animate-in fade-in">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{t('savedNotice')}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </dialog>
  );
}

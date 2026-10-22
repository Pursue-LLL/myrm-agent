'use client';

/**
 * [INPUT]
 * - mobileCockpitTypes: MobileVoiceStagedInputProps
 * - useVoiceRecognition: React hook handling audio recording and real-time speech dictation
 * - lucide-react icons
 *
 * [OUTPUT]
 * - MobileVoiceStagedInput: React component for voice-first staged input box
 *
 * [POS]
 * Mobile Remote Companion voice-first staged input surface avoiding virtual keyboard collisions.
 */

import React, { useState, useEffect, useCallback, ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';
import {
  Mic,
  MicOff,
  Send,
  RotateCcw,
  Trash2,
  X,
  Volume2,
} from 'lucide-react';
import { useVoiceRecognition } from './useVoiceRecognition';
import { MobileVoiceStagedInputProps } from './mobileCockpitTypes';

export const MobileVoiceStagedInput: React.FC<MobileVoiceStagedInputProps> = ({
  isOpen,
  onClose,
  onSend,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('mobileCockpit.voiceStagedInput');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests or SSR
  }

  const [text, setText] = useState<string>('');
  const [unsupportedError, setUnsupportedError] = useState<boolean>(false);

  const {
    isListening,
    transcript,
    toggleRecognition,
    resetTranscript,
    stopRecognition,
  } = useVoiceRecognition({
    onTranscriptChunk: (chunk: string) => {
      setText(chunk);
    },
    onUnsupported: () => {
      setUnsupportedError(true);
    },
  });

  useEffect(() => {
    if (transcript) {
      setText(transcript);
    }
  }, [transcript]);

  useEffect(() => {
    if (!isOpen) {
      stopRecognition();
    }
  }, [isOpen, stopRecognition]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }
    stopRecognition();
    onSend(trimmed);
    setText('');
    resetTranscript();
    onClose();
  }, [text, stopRecognition, onSend, resetTranscript, onClose]);

  const handleClear = useCallback(() => {
    setText('');
    resetTranscript();
  }, [resetTranscript]);

  const handleRedictate = useCallback(() => {
    setText('');
    resetTranscript();
    if (!isListening) {
      toggleRecognition();
    }
  }, [resetTranscript, isListening, toggleRecognition]);

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      aria-label={t('title')}
      className={`fixed inset-0 z-50 m-0 h-full w-full max-h-none max-w-none flex flex-col justify-end bg-black/60 p-0 backdrop-blur-sm transition-opacity border-none ${className}`}
    >
      <div className="w-full rounded-t-3xl border-t border-border/80 bg-background/95 p-5 shadow-2xl backdrop-blur-md pb-[max(1.25rem,env(safe-area-inset-bottom))] animate-in slide-in-from-bottom duration-200">
        <div className="flex items-center justify-between pb-3 border-b border-border/50">
          <div className="flex items-center gap-2">
            <Volume2 className="h-5 w-5 text-primary animate-pulse" />
            <h3 className="font-semibold text-foreground text-base tracking-tight">
              {t('title')}
            </h3>
          </div>
          <button
            type="button"
            aria-label={t('cancel')}
            onClick={() => {
              stopRecognition();
              onClose();
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/60 text-muted-foreground hover:bg-muted"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {unsupportedError ? (
          <div className="my-4 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            {t('unsupported')}
          </div>
        ) : null}

        <div className="my-4 flex flex-col items-center justify-center gap-2 py-2">
          <button
            type="button"
            aria-label={isListening ? t('listening') : t('tapToSpeak')}
            onClick={toggleRecognition}
            className={`relative flex h-20 w-20 items-center justify-center rounded-full transition-all duration-300 shadow-lg ${
              isListening
                ? 'bg-rose-500 text-white ring-8 ring-rose-500/20 scale-105'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}
          >
            {isListening ? (
              <MicOff className="h-9 w-9 animate-bounce" />
            ) : (
              <Mic className="h-9 w-9" />
            )}
          </button>
          <span className="text-xs font-medium text-muted-foreground">
            {isListening ? t('listening') : t('tapToSpeak')}
          </span>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {t('reviewHint')}
            </span>
            <span className="text-[11px] font-mono text-muted-foreground/80">
              {text.length} chars
            </span>
          </div>
          <textarea
            value={text}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
              setText(e.target.value);
            }}
            placeholder={t('placeholder')}
            rows={3}
            className="w-full resize-none rounded-2xl border border-border/80 bg-muted/40 p-3.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2.5">
          <button
            type="button"
            onClick={handleRedictate}
            className="flex h-12 items-center justify-center gap-1.5 rounded-xl border border-border bg-card text-xs font-medium text-foreground hover:bg-accent active:scale-95 transition-all"
          >
            <RotateCcw className="h-4 w-4 text-muted-foreground" />
            <span>{t('retry')}</span>
          </button>

          <button
            type="button"
            onClick={handleClear}
            disabled={!text}
            className="flex h-12 items-center justify-center gap-1.5 rounded-xl border border-border bg-card text-xs font-medium text-foreground hover:bg-accent active:scale-95 transition-all disabled:opacity-40"
          >
            <Trash2 className="h-4 w-4 text-muted-foreground" />
            <span>{t('clear')}</span>
          </button>

          <button
            type="button"
            onClick={handleSend}
            disabled={!text.trim()}
            className="flex h-12 items-center justify-center gap-1.5 rounded-xl bg-primary text-xs font-semibold text-primary-foreground shadow-md hover:bg-primary/90 active:scale-95 transition-all disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
            <span>{t('send')}</span>
          </button>
        </div>
      </div>
    </dialog>
  );
};

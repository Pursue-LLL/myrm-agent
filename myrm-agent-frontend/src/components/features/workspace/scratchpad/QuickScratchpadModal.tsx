'use client';

import React, { useState, useId, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Zap,
  X,
  Copy,
  Check,
  Eye,
  Edit3,
  Trash2,
  FolderPlus,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { useScratchpadStore } from './useScratchpadStore';

export const QuickScratchpadModal: React.FC = () => {
  const t = useTranslations('scratchpad');
  const modalId = useId();

  const isOpen = useScratchpadStore((s) => s.isOpen);
  const draft = useScratchpadStore((s) => s.draft);
  const isPromoting = useScratchpadStore((s) => s.isPromoting);
  const promotionResult = useScratchpadStore((s) => s.promotionResult);
  const error = useScratchpadStore((s) => s.error);

  const closeScratchpad = useScratchpadStore((s) => s.closeScratchpad);
  const setTitle = useScratchpadStore((s) => s.setTitle);
  const setContent = useScratchpadStore((s) => s.setContent);
  const clearDraft = useScratchpadStore((s) => s.clearDraft);
  const promoteToProject = useScratchpadStore((s) => s.promoteToProject);

  const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit');
  const [copied, setCopied] = useState(false);
  const [showPromoteConfirm, setShowPromoteConfirm] = useState(false);
  const [customProjectName, setCustomProjectName] = useState('');

  // Global hotkey: Escape to close
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeScratchpad();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeScratchpad]);

  if (!isOpen) {
    return null;
  }

  const charCount = draft.content.length;
  const wordCount = draft.content.trim() ? draft.content.trim().split(/\s+/).length : 0;
  const lineCount = draft.content ? draft.content.split('\n').length : 0;

  const handleCopy = async () => {
    try {
      const fullText = draft.title ? `# ${draft.title}\n\n${draft.content}` : draft.content;
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  const handleConfirmPromote = async () => {
    try {
      await promoteToProject(customProjectName.trim() || undefined);
      setShowPromoteConfirm(false);
    } catch {
      // Store captures error
    }
  };

  return (
    <dialog
      id={modalId}
      open
      aria-labelledby={`${modalId}-title`}
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full p-4 bg-black/60 backdrop-blur-sm"
    >
      <div className="relative flex flex-col w-full max-w-4xl max-h-[88vh] bg-surface-900 border border-surface-700/80 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-surface-800 bg-surface-900/90">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h2 id={`${modalId}-title`} className="text-base font-semibold text-surface-100">
                {t('title')}
              </h2>
              <p className="text-xs text-surface-400">{t('subtitle')}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              title={t('copyTooltip')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-surface-300 hover:text-surface-100 bg-surface-800/80 hover:bg-surface-800 border border-surface-700/60 rounded-lg transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? t('copySuccess') : t('copyTooltip')}</span>
            </button>

            <button
              type="button"
              onClick={clearDraft}
              title={t('clearDraft')}
              className="p-1.5 text-surface-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>

            <button
              type="button"
              onClick={closeScratchpad}
              title={t('close')}
              className="p-1.5 text-surface-400 hover:text-surface-100 hover:bg-surface-800 rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Title Input */}
        <div className="px-6 pt-4 pb-2">
          <input
            type="text"
            value={draft.title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('titlePlaceholder')}
            className="w-full px-3.5 py-2 text-sm font-medium text-surface-100 bg-surface-800/50 border border-surface-700/50 rounded-xl focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50 placeholder:text-surface-500"
          />
        </div>

        {/* Tab Controls */}
        <div className="flex items-center justify-between px-6 py-2 border-b border-surface-800/60">
          <div className="flex items-center gap-1 bg-surface-800/50 p-1 rounded-lg border border-surface-700/40">
            <button
              type="button"
              onClick={() => setActiveTab('edit')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'edit'
                  ? 'bg-amber-500/20 text-amber-300'
                  : 'text-surface-400 hover:text-surface-200'
              }`}
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>{t('editTab')}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('preview')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'preview'
                  ? 'bg-amber-500/20 text-amber-300'
                  : 'text-surface-400 hover:text-surface-200'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>{t('previewTab')}</span>
            </button>
          </div>

          <span className="text-xs text-surface-400">
            {t('wordCount', { words: wordCount, chars: charCount, lines: lineCount })}
          </span>
        </div>

        {/* Main Content Area */}
        <main className="flex-1 p-6 overflow-y-auto min-h-[280px]">
          {activeTab === 'edit' ? (
            <textarea
              value={draft.content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t('contentPlaceholder')}
              rows={14}
              className="w-full h-full p-4 text-sm font-mono text-surface-200 bg-surface-950/50 border border-surface-800/80 rounded-xl focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50 resize-none placeholder:text-surface-600"
            />
          ) : (
            <article className="p-4 rounded-xl bg-surface-950/40 border border-surface-800/60 min-h-full">
              {draft.content.trim() ? (
                <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap font-sans text-surface-200">
                  {draft.content}
                </div>
              ) : (
                <p className="text-sm text-surface-500 italic text-center py-12">
                  {t('emptyPreview')}
                </p>
              )}
            </article>
          )}

          {/* Promotion Success Notice */}
          {promotionResult && (
            <div className="mt-4 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0 text-emerald-400" />
              <div className="text-xs space-y-1">
                <p className="font-semibold">{t('promotedSuccess')}</p>
                <p className="font-mono text-surface-300">
                  {t('promotedPath', { path: promotionResult.target_directory })}
                </p>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
              {error}
            </div>
          )}
        </main>

        {/* Footer */}
        <footer className="flex items-center justify-between px-6 py-4 border-t border-surface-800 bg-surface-900/90">
          <button
            type="button"
            onClick={closeScratchpad}
            className="px-4 py-2 text-xs font-medium text-surface-300 hover:text-surface-100 bg-surface-800/60 hover:bg-surface-800 rounded-xl transition-colors"
          >
            {t('close')}
          </button>

          {!showPromoteConfirm ? (
            <button
              type="button"
              disabled={isPromoting || (!draft.title.trim() && !draft.content.trim())}
              onClick={() => setShowPromoteConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-amber-950 bg-amber-400 hover:bg-amber-300 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl shadow-lg shadow-amber-500/10 transition-colors"
            >
              {isPromoting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderPlus className="w-4 h-4" />}
              <span>{isPromoting ? t('promoting') : t('promoteButton')}</span>
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={customProjectName}
                onChange={(e) => setCustomProjectName(e.target.value)}
                placeholder={t('targetProjectPlaceholder')}
                className="px-3 py-1.5 text-xs text-surface-100 bg-surface-800 border border-surface-700 rounded-lg focus:outline-none focus:border-amber-500/50"
              />
              <button
                type="button"
                onClick={() => setShowPromoteConfirm(false)}
                className="px-3 py-1.5 text-xs text-surface-400 hover:text-surface-200"
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                disabled={isPromoting}
                onClick={handleConfirmPromote}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-950 bg-amber-400 hover:bg-amber-300 rounded-lg transition-colors"
              >
                {isPromoting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>{t('confirmPromote')}</span>
              </button>
            </div>
          )}
        </footer>
      </div>
    </dialog>
  );
};

/**
 * [INPUT]
 * @/services/presentation::generatePresentation, PresentationArtifactResponse, PresentationGenerateRequest (POS: Presentation API client & types)
 * @/components/features/presentation/PresentationSlidePreviewViewer (POS: High-fidelity presentation previewer)
 * react-i18next::useTranslation (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - PresentationGeneratorModal: Semantic `<dialog>` modal for configuring and generating presentation decks
 *
 * [POS]
 * Presentation Generator Modal Component (Item 16).
 * Single file < 280 lines. Zero `any` types.
 */

'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  generatePresentation,
  type PresentationArtifactResponse,
  type PresentationGenerateRequest,
} from '@/services/presentation';
import { PresentationSlidePreviewViewer } from './PresentationSlidePreviewViewer';

export interface PresentationGeneratorModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTopic?: string;
}

type TemplateStyleType = NonNullable<PresentationGenerateRequest['template_style']>;

export const PresentationGeneratorModal: React.FC<PresentationGeneratorModalProps> = ({
  isOpen,
  onClose,
  defaultTopic = '',
}) => {
  const t = useTranslations('presentation');
  const dialogRef = useRef<HTMLDialogElement>(null);

  const [topic, setTopic] = useState<string>(defaultTopic);
  const [templateStyle, setTemplateStyle] = useState<TemplateStyleType>('enterprise_blue');
  const [slidesCount, setSlidesCount] = useState<number>(5);
  const [enableIllustrations, setEnableIllustrations] = useState<boolean>(true);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<PresentationArtifactResponse | null>(null);

  // Sync native dialog open state
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (isOpen) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else {
      if (dialog.open) {
        dialog.close();
      }
    }
  }, [isOpen]);

  const handleGenerate = useCallback(async () => {
    if (!topic.trim()) {
      return;
    }

    setIsGenerating(true);
    setErrorMessage(null);

    try {
      const response = await generatePresentation({
        topic: topic.trim(),
        template_style: templateStyle,
        slides_count: slidesCount,
        enable_illustrations: enableIllustrations,
      });
      setArtifact(response);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate presentation deck';
      setErrorMessage(msg);
    } finally {
      setIsGenerating(false);
    }
  }, [topic, templateStyle, slidesCount, enableIllustrations]);

  const handleReset = () => {
    setArtifact(null);
    setErrorMessage(null);
  };

  return (
    <dialog
      ref={dialogRef}
      tabIndex={-1}
      onCancel={onClose}
      aria-labelledby="presentation-modal-title"
      className="p-0 bg-transparent backdrop:bg-black/60 backdrop:backdrop-blur-sm max-w-5xl w-full m-auto rounded-2xl shadow-2xl overflow-hidden focus:outline-none"
    >
      <div className="bg-slate-900 border border-white/10 text-slate-100 flex flex-col rounded-2xl max-h-[90vh] overflow-hidden">
        {artifact ? (
          <div className="flex flex-col h-[85vh]">
            <div className="flex justify-between items-center px-6 py-2 bg-slate-950/80 border-b border-white/10">
              <span className="text-xs text-slate-400 font-mono">
                {artifact.file_name}
              </span>
              <button
                type="button"
                onClick={handleReset}
                className="text-xs text-blue-400 hover:text-blue-300 font-medium px-2 py-1 rounded bg-blue-500/10 hover:bg-blue-500/20 transition-colors"
              >
                + New Presentation
              </button>
            </div>
            <div className="flex-1 min-h-0">
              <PresentationSlidePreviewViewer
                artifact={artifact}
                onClose={onClose}
              />
            </div>
          </div>
        ) : (
          <div className="p-8 flex flex-col">
            {/* Header */}
            <div className="flex items-start justify-between pb-6 border-b border-white/10">
              <div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-400/30">
                    P0 · ENTERPRISE PPTX
                  </span>
                  <h2 id="presentation-modal-title" className="text-xl font-bold text-white tracking-tight">
                    {t('modalTitle')}
                  </h2>
                </div>
                <p className="text-sm text-slate-400 mt-1 max-w-2xl">
                  {t('modalSubtitle')}
                </p>
              </div>

              <button
                type="button"
                onClick={onClose}
                aria-label={t('closeAriaLabel')}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Form Body */}
            <div className="py-6 space-y-6">
              {/* Topic Input */}
              <div>
                <label htmlFor="topic-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2">
                  {t('topicLabel')}
                </label>
                <input
                  id="topic-input"
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder={t('topicPlaceholder')}
                  disabled={isGenerating}
                  className="w-full px-4 py-3 rounded-xl bg-slate-950/60 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                />
              </div>

              {/* Template Style Selector */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2">
                  {t('styleLabel')}
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {(
                    [
                      { id: 'enterprise_blue', nameKey: 'styleEnterpriseBlue', color: 'from-blue-600 to-indigo-800' },
                      { id: 'minimal_dark', nameKey: 'styleMinimalDark', color: 'from-zinc-700 to-neutral-900' },
                      { id: 'creative_gradient', nameKey: 'styleCreativeGradient', color: 'from-purple-600 to-pink-800' },
                      { id: 'tech_emerald', nameKey: 'styleTechEmerald', color: 'from-emerald-600 to-teal-800' },
                    ] as const
                  ).map((styleItem) => {
                    const isSelected = templateStyle === styleItem.id;
                    return (
                      <button
                        key={styleItem.id}
                        type="button"
                        onClick={() => setTemplateStyle(styleItem.id as TemplateStyleType)}
                        className={`rounded-xl p-3 border text-left transition-all flex flex-col justify-between ${
                          isSelected
                            ? 'border-blue-500 bg-blue-500/10 ring-2 ring-blue-500/30'
                            : 'border-white/5 bg-slate-950/40 hover:border-white/20'
                        }`}
                      >
                        <div className={`w-full h-8 rounded-lg bg-gradient-to-r ${styleItem.color} mb-2 shadow-inner`} />
                        <span className="text-xs font-medium text-slate-200">
                          {t(styleItem.nameKey)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Slides Count & Illustration Switch */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-2">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <label htmlFor="slides-count-range" className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                      {t('slidesCountLabel')}
                    </label>
                    <span className="font-mono text-sm font-bold text-blue-400">
                      {slidesCount} Pages
                    </span>
                  </div>
                  <input
                    id="slides-count-range"
                    type="range"
                    min={3}
                    max={10}
                    value={slidesCount}
                    onChange={(e) => setSlidesCount(Number(e.target.value))}
                    disabled={isGenerating}
                    className="w-full accent-blue-500 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 mt-1 font-mono">
                    <span>3 min</span>
                    <span>10 max</span>
                  </div>
                </div>

                <div className="flex items-center justify-between p-4 rounded-xl bg-slate-950/40 border border-white/5">
                  <div>
                    <span className="text-xs font-semibold text-slate-200 block">
                      {t('illustrationsLabel')}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Multi-modal visual concepts & layouts
                    </span>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-label={t('illustrationsLabel')}
                    aria-checked={enableIllustrations}
                    onClick={() => setEnableIllustrations(!enableIllustrations)}
                    className={`w-11 h-6 rounded-full transition-colors relative focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      enableIllustrations ? 'bg-blue-600' : 'bg-slate-700'
                    }`}
                  >
                    <span
                      className={`block w-4 h-4 rounded-full bg-white transition-transform ${
                        enableIllustrations ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {errorMessage && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                  {errorMessage}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="pt-4 border-t border-white/10 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                disabled={isGenerating}
                className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleGenerate}
                disabled={!topic.trim() || isGenerating}
                className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-semibold shadow-lg shadow-blue-500/20 transition-all"
              >
                {isGenerating ? (
                  <>
                    <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>{t('generating')}</span>
                  </>
                ) : (
                  <span>{t('generateButton')}</span>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
};

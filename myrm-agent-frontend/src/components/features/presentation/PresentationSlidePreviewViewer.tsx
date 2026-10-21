/**
 * [INPUT]
 * @/services/presentation::PresentationArtifactResponse, getPresentationDownloadUrl (POS: Presentation artifact and download URL)
 * @/components/features/presentation/PresentationSlideCard (POS: High-fidelity slide card renderer)
 * react-i18next::useTranslation (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - PresentationSlidePreviewViewer: Slide deck viewer with navigation, slideshow mode, speaker notes, and download
 *
 * [POS]
 * Presentation Viewer Component (Item 16).
 * Single file < 280 lines. Zero `any` types.
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type { PresentationArtifactResponse } from '@/services/presentation';
import { getPresentationDownloadUrl } from '@/services/presentation';
import { PresentationSlideCard } from './PresentationSlideCard';

export interface PresentationSlidePreviewViewerProps {
  artifact: PresentationArtifactResponse;
  onClose?: () => void;
  initialSlideIndex?: number;
}

export const PresentationSlidePreviewViewer: React.FC<PresentationSlidePreviewViewerProps> = ({
  artifact,
  onClose,
  initialSlideIndex = 0,
}) => {
  const t = useTranslations('presentation');
  const [currentIndex, setCurrentIndex] = useState<number>(initialSlideIndex);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showNotes, setShowNotes] = useState<boolean>(false);

  const totalSlides = artifact.slides.length;
  const currentSlide = artifact.slides[currentIndex] || artifact.slides[0];

  const handlePrev = useCallback(() => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, []);

  const handleNext = useCallback(() => {
    setCurrentIndex((prev) => Math.min(totalSlides - 1, prev + 1));
  }, [totalSlides]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        handlePrev();
      } else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
        e.preventDefault();
        handleNext();
      } else if (e.key === 'Escape' && isFullscreen) {
        e.preventDefault();
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handlePrev, handleNext, isFullscreen]);

  const downloadUrl = getPresentationDownloadUrl(artifact.id);

  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-50 bg-black flex flex-col justify-between p-6 select-none animate-in fade-in">
        {/* Floating Top Controls */}
        <div className="flex items-center justify-between opacity-40 hover:opacity-100 transition-opacity">
          <div className="text-white/80 font-mono text-sm">
            {artifact.topic} · {t('slideCounter', { current: currentIndex + 1, total: totalSlides })}
          </div>
          <button
            type="button"
            onClick={() => setIsFullscreen(false)}
            className="px-3 py-1.5 rounded-lg bg-white/20 text-white text-xs font-medium hover:bg-white/30 transition-colors"
          >
            {t('exitFullscreen')} (ESC)
          </button>
        </div>

        {/* Center Presentation Stage */}
        <div className="flex-1 flex items-center justify-center max-w-6xl w-full mx-auto my-auto">
          {currentSlide && (
            <PresentationSlideCard
              slide={currentSlide}
              templateStyle={artifact.template_style}
              className="max-h-[85vh] w-full"
            />
          )}
        </div>

        {/* Floating Bottom Navigator */}
        <div className="flex items-center justify-center gap-4 opacity-40 hover:opacity-100 transition-opacity">
          <button
            type="button"
            onClick={handlePrev}
            disabled={currentIndex === 0}
            className="px-4 py-2 rounded-lg bg-white/10 text-white text-sm font-medium hover:bg-white/20 disabled:opacity-20 transition-all"
          >
            {t('previousSlide')}
          </button>
          <span className="text-white/60 font-mono text-sm">
            {currentIndex + 1} / {totalSlides}
          </span>
          <button
            type="button"
            onClick={handleNext}
            disabled={currentIndex === totalSlides - 1}
            className="px-4 py-2 rounded-lg bg-white/10 text-white text-sm font-medium hover:bg-white/20 disabled:opacity-20 transition-all"
          >
            {t('nextSlide')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-900/90 text-slate-100 rounded-2xl overflow-hidden border border-white/10 shadow-2xl">
      {/* Top Header Bar */}
      <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-slate-950/60">
        <div>
          <h3 className="font-semibold text-lg text-white truncate max-w-xl">
            {artifact.topic}
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {artifact.file_name} · {(artifact.file_size_bytes / 1024).toFixed(1)} KB · {artifact.total_slides} Slides
          </p>
        </div>

        <div className="flex items-center gap-3">
          <a
            href={downloadUrl}
            download={artifact.file_name}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium shadow-sm transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            {t('downloadPptx')}
          </a>

          <button
            type="button"
            onClick={() => setIsFullscreen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-medium transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0 0l-5-5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
            {t('fullscreenPresentation')}
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label={t('closeAriaLabel')}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Main Workspace: Left Thumbnails + Right Slide Stage */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Left Thumbnails Rail */}
        <aside
          aria-label="Slide thumbnails"
          className="w-56 border-r border-white/10 bg-slate-950/40 p-3 overflow-y-auto space-y-3 shrink-0"
        >
          {artifact.slides.map((s, idx) => {
            const isSelected = idx === currentIndex;
            return (
              <button
                key={`thumb-${s.slide_number}`}
                type="button"
                onClick={() => setCurrentIndex(idx)}
                aria-label={`Go to slide ${s.slide_number}: ${s.title}`}
                className={`w-full text-left rounded-xl p-1.5 border transition-all ${
                  isSelected
                    ? 'border-blue-500 bg-blue-500/10 ring-2 ring-blue-500/30'
                    : 'border-white/5 bg-white/5 hover:border-white/20 hover:bg-white/10'
                }`}
              >
                <PresentationSlideCard
                  slide={s}
                  templateStyle={artifact.template_style}
                  isThumbnail
                  className="pointer-events-none"
                />
                <div className="mt-1 flex items-center justify-between px-1">
                  <span className="text-[10px] font-mono text-slate-400">
                    #{s.slide_number}
                  </span>
                  <span className="text-[10px] text-slate-300 truncate max-w-[120px]">
                    {s.title}
                  </span>
                </div>
              </button>
            );
          })}
        </aside>

        {/* Center Stage & Speaker Notes */}
        <main className="flex-1 flex flex-col p-6 overflow-y-auto items-center justify-between">
          <div className="w-full max-w-4xl my-auto">
            {currentSlide && (
              <PresentationSlideCard
                slide={currentSlide}
                templateStyle={artifact.template_style}
              />
            )}
          </div>

          {/* Speaker Notes Accordion */}
          {currentSlide && currentSlide.speaker_notes && (
            <div className="w-full max-w-4xl mt-4">
              <button
                type="button"
                onClick={() => setShowNotes(!showNotes)}
                className="w-full text-left flex items-center justify-between px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-300 hover:bg-white/10 transition-colors"
              >
                <span className="font-semibold flex items-center gap-2">
                  <svg className="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                  </svg>
                  {t('speakerNotes')}
                </span>
                <span className="text-slate-500">{showNotes ? '▲' : '▼'}</span>
              </button>
              {showNotes && (
                <div className="p-4 mt-1 rounded-xl bg-black/40 border border-white/5 text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap">
                  {currentSlide.speaker_notes}
                </div>
              )}
            </div>
          )}
        </main>
      </div>

      {/* Bottom Nav Footer */}
      <footer className="px-6 py-3 border-t border-white/10 bg-slate-950/60 flex items-center justify-between">
        <button
          type="button"
          onClick={handlePrev}
          disabled={currentIndex === 0}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-20 text-xs font-medium text-slate-200 transition-colors"
        >
          ← {t('previousSlide')}
        </button>

        <span className="text-xs font-mono text-slate-400">
          {t('slideCounter', { current: currentIndex + 1, total: totalSlides })}
        </span>

        <button
          type="button"
          onClick={handleNext}
          disabled={currentIndex === totalSlides - 1}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-20 text-xs font-medium text-slate-200 transition-colors"
        >
          {t('nextSlide')} →
        </button>
      </footer>
    </div>
  );
};

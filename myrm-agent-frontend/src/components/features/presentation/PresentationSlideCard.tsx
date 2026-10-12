/**
 * [INPUT]
 * @/services/presentation::SlideData, SlideLayoutType (POS: Slide structure contract)
 *
 * [OUTPUT]
 * - PresentationSlideCard: High-fidelity 16:9 slide renderer component
 *
 * [POS]
 * Presentation Slide Renderer (Item 16).
 * Single file < 260 lines. Zero `any` types.
 */

import React from 'react';
import type { SlideData, SlideElement } from '@/services/presentation';

export interface PresentationSlideCardProps {
  slide: SlideData;
  templateStyle?: string;
  className?: string;
  isThumbnail?: boolean;
}

const STYLE_THEMES: Record<
  string,
  {
    bgGradient: string;
    cardBg: string;
    textPrimary: string;
    textSecondary: string;
    accentBadge: string;
    borderAccent: string;
  }
> = {
  enterprise_blue: {
    bgGradient: 'from-slate-900 via-indigo-950 to-blue-950 text-white',
    cardBg: 'bg-white/10 backdrop-blur-sm border-blue-400/20 text-slate-100',
    textPrimary: 'text-white',
    textSecondary: 'text-blue-200',
    accentBadge: 'bg-blue-500/20 text-blue-300 border-blue-400/30',
    borderAccent: 'border-blue-500/40',
  },
  minimal_dark: {
    bgGradient: 'from-neutral-950 via-zinc-900 to-black text-white',
    cardBg: 'bg-neutral-800/50 backdrop-blur-sm border-neutral-700/50 text-neutral-200',
    textPrimary: 'text-white',
    textSecondary: 'text-neutral-400',
    accentBadge: 'bg-neutral-700/40 text-neutral-300 border-neutral-600/40',
    borderAccent: 'border-neutral-600',
  },
  creative_gradient: {
    bgGradient: 'from-violet-950 via-purple-900 to-fuchsia-950 text-white',
    cardBg: 'bg-white/10 backdrop-blur-sm border-purple-400/20 text-purple-100',
    textPrimary: 'text-white',
    textSecondary: 'text-purple-200',
    accentBadge: 'bg-purple-500/20 text-purple-300 border-purple-400/30',
    borderAccent: 'border-purple-500/40',
  },
  tech_emerald: {
    bgGradient: 'from-zinc-950 via-emerald-950 to-teal-950 text-white',
    cardBg: 'bg-emerald-950/40 backdrop-blur-sm border-emerald-500/20 text-emerald-100',
    textPrimary: 'text-white',
    textSecondary: 'text-emerald-300',
    accentBadge: 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30',
    borderAccent: 'border-emerald-500/40',
  },
};

function renderElementCard(element: SlideElement, index: number, theme: typeof STYLE_THEMES.enterprise_blue, isThumbnail: boolean) {
  return (
    <div
      key={`elem-${index}`}
      className={`rounded-xl p-4 border flex flex-col justify-between shadow-lg transition-all ${theme.cardBg} ${isThumbnail ? 'text-[8px] p-1.5' : ''}`}
    >
      <div>
        {element.title && (
          <h4 className={`font-semibold tracking-wide ${theme.textPrimary} ${isThumbnail ? 'text-[9px] mb-0.5' : 'text-base mb-1.5'}`}>
            {element.title}
          </h4>
        )}
        {element.body && (
          <p className={`leading-relaxed line-clamp-3 ${theme.textSecondary} ${isThumbnail ? 'text-[7px]' : 'text-xs'}`}>
            {element.body}
          </p>
        )}
        {element.bullet_points && element.bullet_points.length > 0 && (
          <ul className={`mt-2 space-y-1 list-disc list-inside ${theme.textSecondary} ${isThumbnail ? 'text-[7px] space-y-0.5' : 'text-xs'}`}>
            {element.bullet_points.map((point, ptIdx) => (
              <li key={`pt-${ptIdx}`} className="line-clamp-1">{point}</li>
            ))}
          </ul>
        )}
      </div>

      {element.metric_value && (
        <div className={`mt-3 pt-2 border-t border-white/10 flex items-baseline gap-2 ${isThumbnail ? 'mt-1 pt-1' : ''}`}>
          <span className={`font-bold font-mono text-emerald-400 ${isThumbnail ? 'text-[10px]' : 'text-xl'}`}>
            {element.metric_value}
          </span>
          {element.metric_label && (
            <span className={`text-white/60 ${isThumbnail ? 'text-[6px]' : 'text-xs'}`}>
              {element.metric_label}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export const PresentationSlideCard: React.FC<PresentationSlideCardProps> = ({
  slide,
  templateStyle = 'enterprise_blue',
  className = '',
  isThumbnail = false,
}) => {
  const theme = STYLE_THEMES[templateStyle] || STYLE_THEMES.enterprise_blue;

  return (
    <article
      aria-label={`Slide ${slide.slide_number}: ${slide.title}`}
      className={`relative w-full aspect-video rounded-2xl overflow-hidden bg-gradient-to-br shadow-2xl border border-white/10 flex flex-col select-none ${theme.bgGradient} ${className}`}
    >
      {/* Slide Header: Header Banner */}
      <header className={`flex items-start justify-between border-b border-white/10 ${isThumbnail ? 'px-3 py-1.5' : 'px-8 py-5'}`}>
        <div className="flex-1 min-w-0 pr-4">
          <div className="flex items-center gap-2 mb-1">
            <span className={`px-2 py-0.5 rounded-full font-mono font-medium border ${theme.accentBadge} ${isThumbnail ? 'text-[7px] px-1' : 'text-xs'}`}>
              SLIDE #{slide.slide_number}
            </span>
            <span className={`uppercase tracking-wider font-semibold opacity-70 ${isThumbnail ? 'text-[6px]' : 'text-[10px]'}`}>
              {slide.layout.replace(/_/g, ' ')}
            </span>
          </div>
          <h2 className={`font-bold tracking-tight truncate ${theme.textPrimary} ${isThumbnail ? 'text-xs' : 'text-2xl'}`}>
            {slide.title}
          </h2>
          {slide.subtitle && (
            <p className={`truncate mt-0.5 ${theme.textSecondary} ${isThumbnail ? 'text-[8px]' : 'text-sm'}`}>
              {slide.subtitle}
            </p>
          )}
        </div>
        <div className={`text-white/40 font-mono tracking-widest font-bold ${isThumbnail ? 'text-[8px]' : 'text-sm'}`}>
          MYRM · 16:9
        </div>
      </header>

      {/* Slide Body: Layout Variations */}
      <section className={`flex-1 overflow-hidden flex flex-col justify-center ${isThumbnail ? 'p-2.5' : 'p-8'}`}>
        {slide.layout === 'title_hero' && (
          <div className="flex flex-col items-center justify-center text-center max-w-2xl mx-auto my-auto py-4">
            <div className={`w-12 h-1 rounded-full mb-4 bg-gradient-to-r from-blue-400 to-indigo-400 ${isThumbnail ? 'w-6 h-0.5 mb-1.5' : ''}`} />
            <h1 className={`font-extrabold tracking-tight mb-3 ${theme.textPrimary} ${isThumbnail ? 'text-sm mb-1' : 'text-3xl sm:text-4xl'}`}>
              {slide.title}
            </h1>
            {slide.subtitle && (
              <p className={`font-medium max-w-lg ${theme.textSecondary} ${isThumbnail ? 'text-[8px]' : 'text-base sm:text-lg'}`}>
                {slide.subtitle}
              </p>
            )}
            {slide.elements.length > 0 && (
              <div className={`mt-6 flex flex-wrap gap-2 justify-center ${isThumbnail ? 'mt-2 gap-1' : ''}`}>
                {slide.elements.map((el, i) => (
                  <span
                    key={`hero-tag-${i}`}
                    className={`rounded-lg px-3 py-1 font-medium border ${theme.accentBadge} ${isThumbnail ? 'text-[6px] px-1.5 py-0.5' : 'text-xs'}`}
                  >
                    {el.title || el.body}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {slide.layout === 'two_column_comparison' && (
          <div className={`grid grid-cols-2 gap-4 h-full items-stretch ${isThumbnail ? 'gap-1.5' : ''}`}>
            {slide.elements.map((elem, idx) => renderElementCard(elem, idx, theme, isThumbnail))}
          </div>
        )}

        {slide.layout === 'three_card_flow' && (
          <div className={`grid grid-cols-3 gap-4 h-full items-stretch ${isThumbnail ? 'gap-1.5' : ''}`}>
            {slide.elements.map((elem, idx) => renderElementCard(elem, idx, theme, isThumbnail))}
          </div>
        )}

        {slide.layout === 'concept_illustration_focus' && (
          <div className={`grid grid-cols-12 gap-6 h-full items-center ${isThumbnail ? 'gap-2' : ''}`}>
            <div className={`col-span-7 flex flex-col justify-center space-y-3 ${isThumbnail ? 'space-y-1' : ''}`}>
              {slide.elements
                .filter((el) => el.element_type !== 'concept_illustration')
                .map((elem, idx) => renderElementCard(elem, idx, theme, isThumbnail))}
            </div>
            <div className="col-span-5 h-full flex flex-col items-center justify-center">
              <div className={`w-full h-full rounded-xl border border-white/20 bg-white/5 backdrop-blur-md flex flex-col items-center justify-center p-4 text-center ${isThumbnail ? 'p-1' : ''}`}>
                <div className={`rounded-full bg-blue-500/20 p-3 mb-2 text-blue-400 ${isThumbnail ? 'p-1 mb-0.5' : ''}`}>
                  <svg className={`stroke-current ${isThumbnail ? 'w-3 h-3' : 'w-8 h-8'}`} fill="none" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <span className={`font-mono text-white/70 uppercase tracking-widest ${isThumbnail ? 'text-[6px]' : 'text-xs'}`}>
                  Visual Concept
                </span>
                <span className={`text-white/50 text-center line-clamp-2 mt-1 ${isThumbnail ? 'text-[5px]' : 'text-[11px]'}`}>
                  {slide.elements.find((el) => el.illustration_prompt)?.illustration_prompt || 'Multimodal Architecture Diagram'}
                </span>
              </div>
            </div>
          </div>
        )}

        {slide.layout === 'summary_action' && (
          <div className={`flex flex-col justify-center h-full max-w-3xl mx-auto w-full space-y-3 ${isThumbnail ? 'space-y-1' : ''}`}>
            {slide.elements.map((elem, idx) => renderElementCard(elem, idx, theme, isThumbnail))}
          </div>
        )}
      </section>

      {/* Slide Footer */}
      <footer className={`border-t border-white/10 flex items-center justify-between opacity-60 font-mono ${isThumbnail ? 'px-3 py-1 text-[6px]' : 'px-8 py-3 text-xs'}`}>
        <span>CONFIDENTIAL · ENTERPRISE DECK</span>
        <span>PAGE {slide.slide_number}</span>
      </footer>
    </article>
  );
};

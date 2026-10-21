'use client';

/**
 * [INPUT]
 * - digitalSelfTypes::ToneStyle, TONE_STYLE_CONFIGS (POS: Tone style configs.)
 * - lucide-react::Sparkles (POS: Vector indicator.)
 *
 * [OUTPUT]
 * - DigitalSelfToneSelector: Tone style pill toggles for Digital Self drafting.
 *
 * [POS]
 * Compact segmented pill selector enabling rapid switching between formal,
 * semi-formal, friendly, and concise corporate tones.
 */

import React from 'react';
import { Sparkles } from 'lucide-react';
import {
  type ToneStyle,
  TONE_STYLE_CONFIGS,
} from './digitalSelfTypes';

export interface DigitalSelfToneSelectorProps {
  currentTone: ToneStyle;
  onSelectTone: (tone: ToneStyle) => void;
  disabled?: boolean;
  className?: string;
}

export default function DigitalSelfToneSelector({
  currentTone,
  onSelectTone,
  disabled = false,
  className = '',
}: DigitalSelfToneSelectorProps) {
  const allTones: ToneStyle[] = ['formal', 'semi-formal', 'friendly', 'concise'];

  return (
    <div
      data-testid="digital-self-tone-selector"
      className={`inline-flex items-center gap-1 p-0.5 rounded-lg border border-border/40 bg-muted/30 ${className}`}
    >
      <div className="flex items-center gap-1 px-1.5 text-[11px] font-medium text-muted-foreground shrink-0">
        <Sparkles className="w-3 h-3 text-primary/70" aria-hidden="true" />
        <span>语气风格</span>
      </div>

      <div className="flex items-center gap-0.5">
        {allTones.map((toneKey) => {
          const config = TONE_STYLE_CONFIGS[toneKey];
          const isSelected = toneKey === currentTone;

          return (
            <button
              key={toneKey}
              type="button"
              disabled={disabled}
              data-testid={`tone-btn-${toneKey}`}
              onClick={() => {
                if (!disabled) {
                  onSelectTone(toneKey);
                }
              }}
              title={config.description}
              className={`px-2 py-0.5 text-xs font-medium rounded-md transition-all ${
                isSelected
                  ? 'bg-background text-foreground shadow-2xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {config.displayName}
            </button>
          );
        })}
      </div>
    </div>
  );
}

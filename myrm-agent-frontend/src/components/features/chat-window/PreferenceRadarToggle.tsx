'use client';

/**
 * [INPUT]
 * @/services/memory/preferences::getPreferenceRadarState, tunePreferenceRadar, RadarDimensionValues
 * @/components/chat/DynamicPreferenceRadarDrawer::DynamicPreferenceRadarDrawer, RADAR_PRESETS
 * @/lib/utils/classnameUtils::cn
 * next-intl::useTranslations (POS: Internationalization hook)
 *
 * [OUTPUT]
 * PreferenceRadarToggle: Floating satellite toggle button and docked radar drawer for chat window.
 *
 * [POS]
 * Chat window satellite widget for real-time memory preference radar inspection and fine-tuning.
 */

import React, { useState, useCallback, useRef } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { DynamicPreferenceRadarDrawer, RADAR_PRESETS } from '@/components/chat/DynamicPreferenceRadarDrawer';
import {
  getPreferenceRadarState,
  tunePreferenceRadar,
  type PreferenceRadarStateResponse,
  type PreferenceRadarTuneRequest,
  type RadarDimensionValues,
} from '@/services/memory/preferences';
import { cn } from '@/lib/utils/classnameUtils';

const NEUTRAL_DIMENSIONS: RadarDimensionValues = {
  recency: 1.0,
  actionability: 1.0,
  technical_depth: 1.0,
  conciseness: 1.0,
  breadth: 1.0,
};

const dimensionsOf = ({
  recency,
  actionability,
  technical_depth,
  conciseness,
  breadth,
}: PreferenceRadarStateResponse): RadarDimensionValues => ({
  recency,
  actionability,
  technical_depth,
  conciseness,
  breadth,
});

export interface PreferenceRadarToggleProps {
  chatId?: string;
  className?: string;
}

interface SessionRadarToggleProps {
  sessionId: string;
  className?: string;
}

function SessionRadarToggle({ sessionId, className = '' }: SessionRadarToggleProps) {
  const t = useTranslations('chat.preferenceRadar');
  const [isOpen, setIsOpen] = useState(false);
  const [locked, setLocked] = useState(false);
  const [values, setValues] = useState<RadarDimensionValues>(NEUTRAL_DIMENSIONS);
  // Counts the user's edits: what the server answered to a request sent before the latest edit is out of date.
  const editsRef = useRef(0);

  const refresh = useCallback(async () => {
    const editsBefore = editsRef.current;
    try {
      const state = await getPreferenceRadarState(sessionId);
      if (editsRef.current === editsBefore) {
        setValues(dimensionsOf(state));
        setLocked(state.locked);
      }
    } catch {
      // The drawer keeps what it shows; opening it again asks again.
    }
  }, [sessionId]);

  const tune = useCallback(
    async (request: PreferenceRadarTuneRequest) => {
      editsRef.current += 1;
      try {
        await tunePreferenceRadar(sessionId, request);
      } catch {
        // The request has told the user it failed; show what the server really holds.
        await refresh();
      }
    },
    [sessionId, refresh],
  );

  // The server keeps fitting the radar while the user chats, so every opening shows its current state.
  const toggleDrawer = () => {
    if (!isOpen) {
      refresh();
    }
    setIsOpen(!isOpen);
  };

  return (
    <>
      <div className={cn('fixed bottom-24 right-32 z-50 max-sm:bottom-20 max-sm:right-28', className)}>
        <button
          type="button"
          data-testid="preference-radar-toggle-button"
          onClick={toggleDrawer}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-full border border-border/80 shadow-md transition-all duration-200',
            isOpen
              ? 'bg-primary text-primary-foreground scale-105 ring-2 ring-primary/30'
              : 'bg-secondary/90 hover:bg-secondary text-secondary-foreground hover:scale-105',
          )}
          title={t('title')}
          aria-label={t('ariaLabel')}
        >
          <SlidersHorizontal className="h-4 w-4" />
        </button>
      </div>

      <DynamicPreferenceRadarDrawer
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        values={values}
        locked={locked}
        onValueChange={(dimension, value) => {
          setValues((prev) => ({ ...prev, [dimension]: value }));
          tune({ [dimension]: value });
        }}
        onToggleLock={(nextLocked) => {
          setLocked(nextLocked);
          tune({ locked: nextLocked });
        }}
        onReset={() => {
          setValues(NEUTRAL_DIMENSIONS);
          tune({ reset_to_neutral: true });
        }}
        onSelectPreset={(preset) => {
          const presetValues = RADAR_PRESETS[preset].values;
          setValues(presetValues);
          tune(presetValues);
        }}
      />
    </>
  );
}

/** One radar per session: switching sessions starts again from that session's own state instead of keeping the last one's. */
export const PreferenceRadarToggle: React.FC<PreferenceRadarToggleProps> = ({ chatId, className }) => {
  const sessionId = chatId?.trim() || 'default';
  return <SessionRadarToggle key={sessionId} sessionId={sessionId} className={className} />;
};

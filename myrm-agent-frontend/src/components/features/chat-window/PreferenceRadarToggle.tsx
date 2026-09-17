'use client';

/**
 * [INPUT]
 * @/services/memory/preferences::getPreferenceRadarState, tunePreferenceRadar, RadarDimensionValues, RADAR_PRESETS
 * @/components/chat/DynamicPreferenceRadarDrawer::DynamicPreferenceRadarDrawer
 * @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * PreferenceRadarToggle: Floating satellite toggle button and docked radar drawer for chat window.
 *
 * [POS]
 * Chat window satellite widget for real-time memory preference radar inspection and fine-tuning.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import {
  DynamicPreferenceRadarDrawer,
  RadarDimensionValues,
  RADAR_PRESETS,
} from '@/components/chat/DynamicPreferenceRadarDrawer';
import {
  getPreferenceRadarState,
  tunePreferenceRadar,
} from '@/services/memory/preferences';
import { cn } from '@/lib/utils/classnameUtils';

const DEFAULT_DIMENSIONS: RadarDimensionValues = {
  recency: 1.0,
  actionability: 1.0,
  technical_depth: 1.0,
  conciseness: 1.0,
  breadth: 1.0,
};

export interface PreferenceRadarToggleProps {
  chatId?: string;
  className?: string;
}

export const PreferenceRadarToggle: React.FC<PreferenceRadarToggleProps> = ({
  chatId,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [locked, setLocked] = useState(false);
  const [values, setValues] = useState<RadarDimensionValues>(DEFAULT_DIMENSIONS);

  const effectiveSessionId = chatId?.trim() || 'default';

  // Load session radar state on mount or session switch
  useEffect(() => {
    let isMounted = true;
    const fetchState = async () => {
      try {
        const data = await getPreferenceRadarState(effectiveSessionId);
        if (isMounted && data?.dimensions) {
          setValues(data.dimensions);
          setLocked(Boolean(data.locked));
        }
      } catch {
        // Fallback to defaults when offline or initial creation
      }
    };

    fetchState();
    return () => {
      isMounted = false;
    };
  }, [effectiveSessionId]);

  const handleValueChange = useCallback(
    async (dim: keyof RadarDimensionValues, val: number) => {
      const nextValues = { ...values, [dim]: val };
      setValues(nextValues);
      try {
        await tunePreferenceRadar(effectiveSessionId, {
          dimensions: { [dim]: val },
        });
      } catch {
        // Optimistic UI updates
      }
    },
    [effectiveSessionId, values]
  );

  const handleToggleLock = useCallback(
    async (nextLocked: boolean) => {
      setLocked(nextLocked);
      try {
        await tunePreferenceRadar(effectiveSessionId, {
          locked: nextLocked,
        });
      } catch {
        // Optimistic UI updates
      }
    },
    [effectiveSessionId]
  );

  const handleReset = useCallback(async () => {
    setValues(DEFAULT_DIMENSIONS);
    try {
      await tunePreferenceRadar(effectiveSessionId, {
        reset_to_baseline: true,
      });
    } catch {
      // Optimistic UI updates
    }
  }, [effectiveSessionId]);

  const handleSelectPreset = useCallback(
    async (presetKey: 'balanced' | 'code' | 'research') => {
      const targetPreset = RADAR_PRESETS[presetKey];
      if (!targetPreset) {
        return;
      }
      setValues(targetPreset.values);
      try {
        await tunePreferenceRadar(effectiveSessionId, {
          dimensions: targetPreset.values,
        });
      } catch {
        // Optimistic UI updates
      }
    },
    [effectiveSessionId]
  );

  return (
    <>
      <div
        className={cn(
          'fixed bottom-24 right-32 z-50 max-sm:bottom-20 max-sm:right-28',
          className
        )}
      >
        <button
          type="button"
          data-testid="preference-radar-toggle-button"
          onClick={() => setIsOpen((prev) => !prev)}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-full border border-border/80 shadow-md transition-all duration-200',
            isOpen
              ? 'bg-primary text-primary-foreground scale-105 ring-2 ring-primary/30'
              : 'bg-secondary/90 hover:bg-secondary text-secondary-foreground hover:scale-105'
          )}
          title="记忆偏好动态拟合雷达"
          aria-label="偏好雷达"
        >
          <SlidersHorizontal className="h-4 w-4" />
        </button>
      </div>

      <DynamicPreferenceRadarDrawer
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        values={values}
        locked={locked}
        onValueChange={handleValueChange}
        onToggleLock={handleToggleLock}
        onReset={handleReset}
        onSelectPreset={handleSelectPreset}
      />
    </>
  );
};

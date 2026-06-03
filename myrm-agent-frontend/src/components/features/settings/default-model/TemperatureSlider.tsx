'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

interface TemperatureSliderProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
  minLabel?: string;
  maxLabel?: string;
  hint?: string;
}

const TemperatureSlider = memo<TemperatureSliderProps>(
  ({ value, onChange, min = 0, max = 2, step = 0.1, label, minLabel, maxLabel, hint }) => {
    const t = useTranslations('settings.defaultModel');

    const percentage = ((value - min) / (max - min)) * 100;

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-foreground">{label ?? t('temperature')}</label>
          <span className="text-base font-mono font-semibold text-primary bg-primary/10 px-3 py-1 rounded-lg">
            {value.toFixed(1)}
          </span>
        </div>

        <div className="relative py-2">
          <div className="relative h-3 rounded-full bg-border overflow-hidden">
            <div
              className="absolute top-0 left-0 h-full bg-gradient-to-r from-primary/80 to-primary rounded-full transition-all duration-150"
              style={{ width: `${percentage}%` }}
            />
          </div>

          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />

          <div
            className="absolute top-1/2 -translate-y-1/2 w-5 h-5 bg-white dark:bg-foreground rounded-full shadow-lg border-2 border-primary pointer-events-none transition-all duration-150"
            style={{ left: `calc(${percentage}% - 10px)` }}
          />
        </div>

        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            {min} ({minLabel ?? t('precise')})
          </span>
          <span className="text-center">{hint ?? t('temperatureHint')}</span>
          <span>
            {max} ({maxLabel ?? t('creative')})
          </span>
        </div>
      </div>
    );
  },
);

TemperatureSlider.displayName = 'TemperatureSlider';

export default TemperatureSlider;

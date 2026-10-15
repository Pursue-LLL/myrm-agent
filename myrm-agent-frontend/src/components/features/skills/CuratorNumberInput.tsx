'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { Input } from '@/components/primitives/input';

interface CuratorNumberInputProps {
  value: number;
  min: number;
  max?: number;
  /** An integer step makes the field integer-only; any other step allows decimals. */
  step?: number;
  onCommit: (value: number) => void;
  className?: string;
}

function parseDraft(text: string): number | null {
  if (text.trim() === '') {
    return null;
  }
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Numeric threshold field that never hands an unsafe value to the form.
 *
 * The text stays free-form while typing; a value is committed as soon as it is inside
 * [min, max]. On blur anything else is rounded and clamped into range, and an empty field
 * reverts to the last committed value instead of becoming 0.
 */
const CuratorNumberInput = memo(
  ({ value, min, max = Number.POSITIVE_INFINITY, step = 1, onCommit, className }: CuratorNumberInputProps) => {
    const [draft, setDraft] = useState(String(value));
    const integerOnly = Number.isInteger(step);

    // Follow committed changes (e.g. the saved response) without rewriting what the user typed.
    useEffect(() => {
      setDraft((prev) => (parseDraft(prev) === value ? prev : String(value)));
    }, [value]);

    const handleChange = useCallback(
      (text: string) => {
        setDraft(text);
        const parsed = parseDraft(text);
        const inRange = parsed !== null && parsed >= min && parsed <= max;
        if (inRange && (!integerOnly || Number.isInteger(parsed)) && parsed !== value) {
          onCommit(parsed);
        }
      },
      [min, max, integerOnly, value, onCommit],
    );

    const handleBlur = useCallback(() => {
      const parsed = parseDraft(draft);
      if (parsed === null) {
        setDraft(String(value));
        return;
      }
      const normalized = Math.min(max, Math.max(min, integerOnly ? Math.round(parsed) : parsed));
      setDraft(String(normalized));
      if (normalized !== value) {
        onCommit(normalized);
      }
    }, [draft, min, max, integerOnly, value, onCommit]);

    return (
      <Input
        type="number"
        min={min}
        max={Number.isFinite(max) ? max : undefined}
        step={step}
        value={draft}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={handleBlur}
        className={className}
      />
    );
  },
);

CuratorNumberInput.displayName = 'CuratorNumberInput';

export default CuratorNumberInput;

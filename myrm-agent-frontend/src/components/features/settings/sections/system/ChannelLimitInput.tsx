'use client';

/**
 * [INPUT]
 * - react::memo, useState (POS: React core and state hook)
 *
 * [OUTPUT]
 * - ChannelLimitInput: Inline daily-limit box of a channel budget; saves on blur and shows the limit in force whenever
 *   the user is not typing.
 *
 * [POS]
 * Leaf input of the channel budget panel. What it shows is derived from the limit in force, so a number that was not
 * stored, or a box left empty, never stays on screen.
 */

import { memo, useState } from 'react';

interface ChannelLimitInputProps {
  /** The limit in force. */
  value: number;
  /** Saves the typed limit; settles once the save has finished, whether or not it was stored. */
  onSave: (limit: number) => Promise<void>;
}

const ChannelLimitInput = memo<ChannelLimitInputProps>(({ value, onSave }) => {
  // null while the user is not typing, so the box can never disagree with the limit in force.
  const [draft, setDraft] = useState<string | null>(null);

  const commit = async () => {
    const limit = parseFloat(draft ?? '');
    if (!isNaN(limit) && limit !== value) {
      await onSave(limit);
    }
    setDraft(null);
  };

  return (
    <input
      type="number"
      min={0.01}
      max={10000}
      step={0.5}
      value={draft ?? String(value)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      className="w-20 text-right text-xs font-mono px-1.5 py-1 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
    />
  );
});
ChannelLimitInput.displayName = 'ChannelLimitInput';

export default ChannelLimitInput;

'use client';

/**
 * [INPUT]
 * - react::memo, useState (POS: React core and state hook)
 *
 * [OUTPUT]
 * - ChannelLimitInput: Inline daily-limit box of a channel budget; saves on blur, then shows the limit in force again.
 *
 * [POS]
 * Leaf input of the channel budget panel. Apart from text no blur has handled yet, the box shows the limit in force: a
 * number that was not stored, or a box left empty, does not outlive the blur that handled it, while text typed during a
 * save is the next edit and stays.
 */

import { memo, useState } from 'react';

interface ChannelLimitInputProps {
  /** The limit in force. */
  value: number;
  /** Accessible name of the box, which has no label element of its own. */
  label: string;
  /** Saves the typed limit; settles once the save has finished, whether or not it was stored. */
  onSave: (limit: number) => Promise<void>;
}

const ChannelLimitInput = memo<ChannelLimitInputProps>(({ value, label, onSave }) => {
  // null while the user has typed nothing that a blur has not handled yet, so the box shows the limit in force.
  const [draft, setDraft] = useState<string | null>(null);

  const commit = async () => {
    const typed = draft;
    const limit = parseFloat(typed ?? '');
    if (!isNaN(limit) && limit !== value) {
      await onSave(limit);
    }
    // Only the text this blur handled is dropped: whatever was typed while the save was in flight is the next edit.
    setDraft((current) => (current === typed ? null : current));
  };

  return (
    <input
      type="number"
      aria-label={label}
      min={0.01}
      max={10000}
      step="any"
      value={draft ?? String(value)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      className="w-20 text-right text-xs font-mono px-1.5 py-1 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
    />
  );
});
ChannelLimitInput.displayName = 'ChannelLimitInput';

export default ChannelLimitInput;

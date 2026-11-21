'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n support)
 * - @/lib/utils/classnameUtils (POS: Class name merge helper)
 *
 * [OUTPUT]
 * - ChannelGroupPicker: The groups a channel can be added for, each a chip that fills the key box when picked.
 *
 * [POS]
 * Picker of the add form. It offers the budget keys the server already stores chats under, so a key is picked instead
 * of typed from a provider's chat id. It says nothing until it has something to show (no answer yet, or the lookup
 * failed), and says so when no group is left to pick. A chip shows its whole key, breaking it across lines when the box
 * is narrower, so two groups never look alike.
 */

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

interface ChannelGroupPickerProps {
  /** Budget keys to offer; `null` while there is nothing to say yet: not answered, or the lookup failed. */
  keys: readonly string[] | null;
  /** The key in the form's box, which marks the chip it equals. */
  selected: string;
  onPick: (channelKey: string) => void;
}

const ChannelGroupPicker = ({ keys, selected, onPick }: ChannelGroupPickerProps) => {
  const t = useTranslations('settings.channelBudget');

  if (keys === null) {
    return null;
  }
  if (keys.length === 0) {
    return <p className="text-xs text-muted-foreground">{t('knownGroupsEmpty')}</p>;
  }
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground">{t('knownGroupsTitle')}</p>
      <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
        {keys.map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={key === selected}
            onClick={() => onPick(key)}
            className={cn(
              'max-w-full break-all px-2.5 py-1 text-left text-xs font-mono rounded-full border transition-colors',
              key === selected
                ? 'border-primary/60 bg-primary/10 text-foreground'
                : 'border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            {key}
          </button>
        ))}
      </div>
    </div>
  );
};

export default ChannelGroupPicker;

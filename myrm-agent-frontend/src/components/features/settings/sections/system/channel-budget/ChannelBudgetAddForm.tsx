'use client';

/**
 * [INPUT]
 * - react::useState (POS: React state hook)
 * - next-intl::useTranslations (POS: i18n support)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 * - @/lib/utils/toast (POS: Toast wrapper)
 * - @/services/budget (POS: Channel budget API types)
 * - ./channelLimit (POS: Range of a channel's daily limit)
 *
 * [OUTPUT]
 * - ChannelBudgetAddForm: The form that adds a channel: its key, an optional label and its daily limit.
 *
 * [POS]
 * Add form of the channel budget panel. The limit is held as the text of its box and read on Save, so the box can be
 * emptied and retyped; Save stays off while the key or the limit is empty and sends nothing for a limit outside the
 * stored range, which is explained instead. The form tracks its own request, apart from the saves of the channel
 * cards. What was typed is kept when the form is cancelled or its request fails, and starts again from the defaults
 * once a channel has been added.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader, IconSave } from '@/components/features/icons/PremiumIcons';
import { toast } from '@/lib/utils/toast';
import type { ChannelBudgetPolicyFields } from '@/services/budget';
import { CHANNEL_LIMIT_MAX_USD, CHANNEL_LIMIT_MIN_USD, isChannelLimitInRange } from './channelLimit';

/** The limit a new channel starts with, as the text of its box. */
const DEFAULT_LIMIT_USD = '2';
/** The share of its limit at which a new channel starts to warn. */
const DEFAULT_WARNING_THRESHOLD = 0.8;

interface ChannelBudgetAddFormProps {
  open: boolean;
  onClose: () => void;
  /** Creates the policy of a channel; resolves to whether it was stored, once the list has been read back. */
  onCreate: (channelKey: string, policy: ChannelBudgetPolicyFields) => Promise<boolean>;
}

const ChannelBudgetAddForm = ({ open, onClose, onCreate }: ChannelBudgetAddFormProps) => {
  const t = useTranslations('settings.channelBudget');
  const [channelKey, setChannelKey] = useState('');
  const [label, setLabel] = useState('');
  // Text, not a number: a number box that ignores what is not a number cannot be emptied to type a new amount.
  const [limitText, setLimitText] = useState(DEFAULT_LIMIT_USD);
  const [submitting, setSubmitting] = useState(false);
  // NaN while the box is empty, which keeps Save off until an amount is typed.
  const limitUsd = parseFloat(limitText);

  const submit = async () => {
    if (!isChannelLimitInRange(limitUsd)) {
      toast.warning(t('limitOutOfRange', { min: CHANNEL_LIMIT_MIN_USD, max: CHANNEL_LIMIT_MAX_USD }));
      return;
    }
    setSubmitting(true);
    let created = false;
    try {
      created = await onCreate(channelKey, {
        daily_limit_usd: limitUsd,
        warning_threshold: DEFAULT_WARNING_THRESHOLD,
        enabled: true,
        label,
      });
    } finally {
      setSubmitting(false);
    }
    if (created) {
      setChannelKey('');
      setLabel('');
      setLimitText(DEFAULT_LIMIT_USD);
      onClose();
    }
  };

  // The form stays mounted while it is closed, which is what keeps a cancelled draft.
  if (!open) {
    return null;
  }

  return (
    <div className="p-3 rounded-lg border border-dashed border-primary/30 bg-primary/5 space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={channelKey}
          onChange={(e) => setChannelKey(e.target.value)}
          placeholder={t('channelKeyPlaceholder')}
          className="flex-1 min-w-0 text-sm px-2.5 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={t('labelPlaceholder')}
          className="sm:w-32 text-sm px-2.5 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">{t('dailyLimit')}:</span>
          <span className="text-xs text-muted-foreground">$</span>
          <input
            type="number"
            aria-label={t('dailyLimit')}
            min={CHANNEL_LIMIT_MIN_USD}
            max={CHANNEL_LIMIT_MAX_USD}
            step="any"
            value={limitText}
            onChange={(e) => setLimitText(e.target.value)}
            className="w-20 text-right text-sm font-mono px-2 py-1 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div className="flex-1" />
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors"
        >
          {t('cancel')}
        </button>
        <button
          onClick={submit}
          disabled={submitting || !channelKey.trim() || isNaN(limitUsd)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {submitting ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconSave className="w-3.5 h-3.5" />}
          {t('save')}
        </button>
      </div>
    </div>
  );
};

export default ChannelBudgetAddForm;

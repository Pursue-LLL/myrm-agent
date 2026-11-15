'use client';

/**
 * [INPUT]
 * - PremiumIcons (POS: premium glyph set, no native emoji)
 *
 * [OUTPUT]
 * - KeyStatusBadge: configured / key required / connection failed marker beside a provider label.
 * - MediaApiKeyForm: the "this provider has no key yet" card with a hidden-by-default key field and a save button.
 * - selectionPlaceholderKey: which prompt an empty dropdown shows.
 *
 * [POS]
 * Pieces the image, video and speech cards of the media settings share, so a credential reads and behaves the same on
 * all three.
 */

import { useState } from 'react';
import {
  IconAlertCircle,
  IconCheckCircle,
  IconEye,
  IconEyeOff,
  IconLoader,
  IconSave,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';

type TranslateMediaSettings = (key: 'configured' | 'needsApiKey' | 'connectionFailed') => string;

export type KeyStatus = 'configured' | 'needsKey' | 'failed';

export function KeyStatusBadge({ status, t }: { status: KeyStatus; t: TranslateMediaSettings }) {
  if (status === 'configured') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
        <IconCheckCircle className="h-3 w-3" />
        {t('configured')}
      </span>
    );
  }
  if (status === 'needsKey') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
        <IconAlertCircle className="h-3 w-3" />
        {t('needsApiKey')}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-red-500">
      <IconXCircle className="h-3 w-3" />
      {t('connectionFailed')}
    </span>
  );
}

interface MediaApiKeyFormProps {
  hint: string;
  label: string;
  placeholder: string;
  saveLabel: string;
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
  saving: boolean;
}

export function MediaApiKeyForm({
  hint,
  label,
  placeholder,
  saveLabel,
  value,
  onChange,
  onSave,
  saving,
}: MediaApiKeyFormProps) {
  const [revealed, setRevealed] = useState(false);

  return (
    <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30">
      <p className="text-xs text-amber-700 dark:text-amber-400">{hint}</p>
      <div className="space-y-2">
        <label className="text-xs font-medium text-foreground">{label}</label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={revealed ? 'text' : 'password'}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholder}
              className="w-full rounded-full border border-border bg-background px-3 py-1.5 pr-10 text-sm"
            />
            <button
              type="button"
              onClick={() => setRevealed(!revealed)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {revealed ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
            </button>
          </div>
          <button
            type="button"
            onClick={onSave}
            disabled={!value.trim() || saving}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {saving ? <IconLoader className="h-3 w-3 animate-spin" /> : <IconSave className="h-3 w-3" />}
            {saveLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * What an empty dropdown asks for: a first choice, or a new one because the stored choice is no longer on offer (for
 * example a model its vendor has retired).
 */
export function selectionPlaceholderKey(
  stored: string,
  options: ReadonlyArray<{ value: string }>,
): 'selectPlaceholder' | 'reselectPlaceholder' {
  return stored && !options.some((option) => option.value === stored) ? 'reselectPlaceholder' : 'selectPlaceholder';
}

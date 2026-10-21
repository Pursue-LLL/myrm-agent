'use client';

/**
 * [INPUT]
 * - @/lib/instance-archive/errors::archiveErrorMessageKey (POS: localized copy for stable error codes)
 *
 * [OUTPUT]
 * - ArchiveErrorNotice: inline alert showing the localized message for a failed backup call
 *
 * [POS]
 * Shared failure surface of the export, import and restore flows; never shows server wording.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { WarningCircle } from '@phosphor-icons/react';
import { archiveErrorMessageKey } from '@/lib/instance-archive/errors';

interface ArchiveErrorNoticeProps {
  code: string;
}

/** Localized, technical-detail-free message for a stable error code. */
export const ArchiveErrorNotice = memo(function ArchiveErrorNotice({ code }: ArchiveErrorNoticeProps) {
  const t = useTranslations('instanceArchive.errors');
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive"
    >
      <WarningCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" />
      <span className="leading-relaxed">{t(archiveErrorMessageKey(code))}</span>
    </div>
  );
});

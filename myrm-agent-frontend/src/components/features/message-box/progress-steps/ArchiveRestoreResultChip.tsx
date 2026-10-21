/**
 * [INPUT]
 * - @/store/chat/types::ArchiveRestoreResultPayload (POS: typed archive restore result DTO)
 *
 * [OUTPUT]
 * - ArchiveRestoreResultChip: compact UI proof that a requested archive range was restored.
 *
 * [POS]
 * Progress-step restore result view. Shows only bounded metadata; restored content stays in the Agent prompt.
 */

import { useTranslations } from 'next-intl';
import type { ArchiveRestoreResultPayload } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';

type ArchiveRestoreResultChipProps = {
  result: ArchiveRestoreResultPayload;
};

const formatNumber = (value: number): string => new Intl.NumberFormat().format(value);

export const ArchiveRestoreResultChip = ({ result }: ArchiveRestoreResultChipProps) => {
  const t = useTranslations('progressSteps');
  const range = `${result.start_line}-${result.end_line}`;
  const details = [
    t('archiveRestoreResultRange', { range }),
    t('archiveRestoreResultTokens', { tokens: formatNumber(result.estimated_tokens) }),
    t('archiveRestoreResultBytes', { bytes: formatNumber(result.restored_bytes) }),
    t('archiveRestoreResultArchive', { path: result.archive_path }),
  ];

  return (
    <div
      className={cn(
        'mt-2 space-y-2 rounded-lg border px-3 py-2.5 text-xs',
        'border-emerald-500/25 bg-emerald-500/10 text-foreground',
      )}
    >
      <p className="leading-relaxed text-foreground/85">
        {t('archiveRestoreResultSummary', {
          lines: formatNumber(result.restored_line_count),
          tokens: formatNumber(result.estimated_tokens),
        })}
      </p>
      <p className="break-all rounded-md border border-emerald-500/15 bg-background/60 px-2 py-1 font-mono text-[11px]">
        {result.restore_arg}
      </p>
      <div className="space-y-1 rounded-md border border-emerald-500/15 bg-background/45 px-2.5 py-2 text-[11px] text-foreground/75">
        {details.map((detail) => (
          <p key={detail} className="break-words leading-relaxed">
            {detail}
          </p>
        ))}
      </div>
    </div>
  );
};

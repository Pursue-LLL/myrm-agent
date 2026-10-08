'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { IconFileText } from '@/components/features/icons/PremiumIcons';
import { Checkbox } from '@/components/primitives/checkbox';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { cn } from '@/lib/utils/classnameUtils';
import type { SecretKind } from '@/services/skill';

import type { IgnoredRedactions, RedactionFindings } from './useRedactionDecisions';

interface RedactionReviewProps {
  findings: RedactionFindings;
  ignored: IgnoredRedactions;
  onToggle: (path: string, index: number) => void;
  onToggleAll: (path: string, total: number) => void;
  disabled?: boolean;
}

/**
 * Per-file diff of what an export would redact. A checked finding is redacted;
 * unchecking keeps the original text in the package (an explicit author decision).
 */
const RedactionReview = memo(({ findings, ignored, onToggle, onToggleAll, disabled = false }: RedactionReviewProps) => {
  const t = useTranslations('common.redactionReview');
  // A kind this client has no sentence for still reads as a sentence, never as a raw key.
  const kindLabel = (kind: SecretKind) => (t.has(`kinds.${kind}`) ? t(`kinds.${kind}`) : t('kinds.unknown'));

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center gap-2 border-b bg-muted/60 px-3 py-2 text-sm font-medium">
        <IconFileText className="h-4 w-4 text-muted-foreground" />
        {t('title')}
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {Object.entries(findings).map(([path, items]) => {
          const keptCount = (ignored[path] ?? []).length;
          return (
            <section key={path} className="border-b last:border-b-0">
              <div className="flex items-center justify-between gap-3 bg-muted/40 px-3 py-1.5">
                <span className="min-w-0 truncate font-mono text-xs" title={path}>
                  {path}
                </span>
                <div className="flex shrink-0 items-center gap-2">
                  <Checkbox
                    id={`redaction-all-${path}`}
                    checked={keptCount === 0}
                    disabled={disabled}
                    onCheckedChange={() => onToggleAll(path, items.length)}
                    className="h-3.5 w-3.5"
                  />
                  <label
                    htmlFor={`redaction-all-${path}`}
                    className="cursor-pointer select-none text-[11px] text-muted-foreground"
                  >
                    {t('toggleAll')}
                  </label>
                </div>
              </div>
              <ul className="space-y-3 p-3">
                {items.map((item, index) => {
                  const kept = (ignored[path] ?? []).includes(index);
                  const kindsLabel = item.kinds.map(kindLabel).join(' / ');
                  return (
                    <li
                      key={index}
                      className={cn(
                        'overflow-hidden rounded-md border font-mono text-xs transition-opacity',
                        kept && 'opacity-60',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2 border-b bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <Checkbox
                            id={`redaction-${path}-${index}`}
                            checked={!kept}
                            disabled={disabled}
                            onCheckedChange={() => onToggle(path, index)}
                            className="h-3.5 w-3.5"
                          />
                          <label htmlFor={`redaction-${path}-${index}`} className="cursor-pointer select-none">
                            {t('line', { number: item.line_number })}
                          </label>
                        </div>
                        <span className="min-w-0 truncate text-amber-600 dark:text-amber-400" title={kindsLabel}>
                          {kindsLabel}
                        </span>
                      </div>
                      <div className="divide-y">
                        <div className="overflow-x-auto whitespace-pre bg-red-500/10 p-2 text-red-700 dark:text-red-400">
                          <span className="mr-2 select-none opacity-50">-</span>
                          {item.original}
                        </div>
                        {!kept && (
                          <div className="overflow-x-auto whitespace-pre bg-emerald-500/10 p-2 text-emerald-700 dark:text-emerald-400">
                            <span className="mr-2 select-none opacity-50">+</span>
                            {item.redacted}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </ScrollArea>
    </div>
  );
});

RedactionReview.displayName = 'RedactionReview';

export default RedactionReview;

'use client';

import { memo, type ComponentType, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';

import { IconCheck, IconX, type IconProps } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';

interface ImportSectionProps {
  icon: ComponentType<IconProps>;
  title: string;
  onSelectAll: () => void;
  onSkipAll: () => void;
  children: ReactNode;
}

/** A titled, bordered list of importable components with bulk select / skip. */
export const ImportSection = memo(({ icon: Icon, title, onSelectAll, onSkipAll, children }: ImportSectionProps) => {
  const t = useTranslations('settings.plugins.import');
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="flex min-w-0 items-center gap-2 text-base font-medium">
          <Icon className="h-4 w-4 shrink-0 text-primary" />
          <span className="truncate">{title}</span>
        </h4>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onSelectAll}>
            {t('actions.selectAll')}
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onSkipAll}>
            {t('actions.skipAll')}
          </Button>
        </div>
      </div>
      <div className="divide-y rounded-xl border bg-background">{children}</div>
    </div>
  );
});
ImportSection.displayName = 'ImportSection';

interface ResolutionToggleProps {
  active: boolean;
  label: string;
  disabled?: boolean;
  onClick: () => void;
}

/** Two-state include / skip control used by rows that have a single way to be imported. */
export const ResolutionToggle = memo(({ active, label, disabled, onClick }: ResolutionToggleProps) => (
  <Button
    variant={active ? 'default' : 'ghost'}
    size="sm"
    className="h-7 px-2 text-xs"
    disabled={disabled}
    onClick={onClick}
  >
    {active ? <IconCheck className="mr-1 h-3 w-3" /> : <IconX className="mr-1 h-3 w-3" />}
    {label}
  </Button>
));
ResolutionToggle.displayName = 'ResolutionToggle';

type NoteTone = 'neutral' | 'caution' | 'danger';

const NOTE_TONES: Record<NoteTone, string> = {
  neutral: 'text-muted-foreground',
  caution: 'text-amber-600 dark:text-amber-400',
  danger: 'text-destructive',
};

/** One short explanatory line under a row; tone carries the severity. */
export function Note({ tone = 'neutral', children }: { tone?: NoteTone; children: ReactNode }) {
  return <p className={cn('mt-0.5 text-xs', NOTE_TONES[tone])}>{children}</p>;
}

const MAX_LISTED_NAMES = 4;

/** Keeps long package-supplied lists readable: the first few names, then a count. */
export function listNames(names: string[]): string {
  const shown = names.slice(0, MAX_LISTED_NAMES).join(', ');
  const hidden = names.length - MAX_LISTED_NAMES;
  return hidden > 0 ? `${shown}, +${hidden}` : shown;
}

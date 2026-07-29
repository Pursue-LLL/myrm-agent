'use client';

/**
 * [INPUT]
 * next-intl (POS: Settings Wiki i18n)
 *
 * [OUTPUT]
 * WikiScopeChip: scoped vault label badge for destructive HITL actions
 *
 * [POS]
 * Settings Wiki scope visibility chip for Pending approve and Queue controls.
 */

import { useTranslations } from 'next-intl';
import { Badge } from '@/components/primitives/badge';

interface WikiScopeChipProps {
  scopeLabel: string;
}

export function WikiScopeChip({ scopeLabel }: WikiScopeChipProps) {
  const t = useTranslations('settings.wiki');
  return (
    <Badge variant="outline" className="text-xs font-normal text-muted-foreground">
      {t('scopeChip.label', { scope: scopeLabel })}
    </Badge>
  );
}

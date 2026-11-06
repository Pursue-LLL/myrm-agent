'use client';

/**
 * [INPUT]
 * - thinkingPermissionTypes::PermissionTier, PERMISSION_TIER_CONFIGS (POS: Permission tier configs.)
 * - usePermissionTierStore::usePermissionTierStore (POS: Reactive permission mode store.)
 * - @/components/primitives/dropdown-menu (POS: Portaled menu, so the toolbar scroller cannot clip it.)
 * - lucide-react::ShieldCheck, Zap, Rocket, ChevronDown, Check (POS: Vector icons.)
 *
 * [OUTPUT]
 * - PermissionModeTierSwitcher: 3-tier capsule menu for agent autonomy & security gates.
 *
 * [POS]
 * Embedded input toolbar switcher allowing users to dynamically switch between Strict
 * guardrails, Semi-Auto agile code execution, and Full-Auto sandbox autonomy. The menu renders
 * in a portal: the toolbar is a horizontal scroller, which clips any in-flow absolute popup.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck, Zap, Rocket, ChevronDown, Check } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { type PermissionTier, PERMISSION_TIER_CONFIGS } from './thinkingPermissionTypes';
import { usePermissionTierStore } from './usePermissionTierStore';

export interface PermissionModeTierSwitcherProps {
  className?: string;
  disabled?: boolean;
}

const TIER_KEYS = Object.keys(PERMISSION_TIER_CONFIGS) as PermissionTier[];

function renderTierIcon(tier: PermissionTier, iconClassName: string = 'w-3.5 h-3.5') {
  if (tier === 'strict') {
    return <ShieldCheck className={iconClassName} aria-hidden="true" />;
  }
  if (tier === 'semi-auto') {
    return <Zap className={iconClassName} aria-hidden="true" />;
  }
  return <Rocket className={iconClassName} aria-hidden="true" />;
}

export default function PermissionModeTierSwitcher({
  className = '',
  disabled = false,
}: PermissionModeTierSwitcherProps) {
  const t = useTranslations('thinkingPermission');
  const currentTier = usePermissionTierStore((state) => state.tier);
  const setTier = usePermissionTierStore((state) => state.setTier);

  const currentConfig = PERMISSION_TIER_CONFIGS[currentTier];

  return (
    <div data-testid="permission-mode-tier-switcher" className={cn('inline-flex items-center', className)}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={disabled}>
          <button
            type="button"
            disabled={disabled}
            data-testid="permission-tier-trigger"
            className={cn(
              'group inline-flex h-8 items-center gap-1.5 px-2 text-xs font-medium rounded-lg border transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed',
              currentConfig.borderColorClass,
              currentConfig.badgeBgClass,
              currentConfig.colorClass,
            )}
            title={t('permissionCurrent', {
              label: t(currentConfig.labelKey),
              description: t(currentConfig.descriptionKey),
            })}
          >
            {renderTierIcon(currentTier)}
            <span>{t(currentConfig.labelKey)}</span>
            <ChevronDown
              className="w-3 h-3 transition-transform duration-200 group-data-[state=open]:rotate-180"
              aria-hidden="true"
            />
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent
          align="start"
          side="top"
          sideOffset={6}
          data-testid="permission-tier-menu"
          className="w-64 rounded-lg border-border/80 bg-popover/95 p-1.5 shadow-lg backdrop-blur-md"
        >
          <DropdownMenuLabel className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('permissionMenuTitle')}
          </DropdownMenuLabel>
          <DropdownMenuSeparator className="mx-0 my-1 bg-border/40" />

          {TIER_KEYS.map((tierKey) => {
            const config = PERMISSION_TIER_CONFIGS[tierKey];
            const isSelected = tierKey === currentTier;

            return (
              <DropdownMenuItem
                key={tierKey}
                role="menuitemradio"
                aria-checked={isSelected}
                data-testid={`permission-option-${tierKey}`}
                onSelect={() => setTier(tierKey)}
                className={cn(
                  'cursor-pointer items-start gap-2 rounded-lg p-2 text-left',
                  isSelected
                    ? 'bg-muted/80 text-foreground font-medium'
                    : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground',
                )}
              >
                <div className={cn('mt-0.5 shrink-0', config.colorClass)}>{renderTierIcon(tierKey, 'w-4 h-4')}</div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-foreground">{t(config.labelKey)}</span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-primary" aria-hidden="true" />}
                  </div>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{t(config.descriptionKey)}</p>
                </div>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

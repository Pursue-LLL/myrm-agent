'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import useCompanionStore from '@/store/useCompanionStore';

import { generateCompanion, HATS, SPECIES } from './companionGenerator';
import { SPECIES_ICON_MAP, HAT_ICON_MAP } from './CompanionIcons';
import { getSpeciesAsset } from './companionAssets';

import type { Hat, Species } from './companionGenerator';

interface CompanionSettingsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function SpeciesPickerItem({
  species,
  isSelected,
  disabled,
  onClick,
}: {
  species: string;
  isSelected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const Icon = SPECIES_ICON_MAP[species];
  const asset = getSpeciesAsset(species);

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={asset.label}
      className={cn(
        'flex items-center justify-center rounded-full p-1.5 transition-all',
        isSelected
          ? 'bg-primary/15 ring-1 ring-primary text-primary'
          : 'hover:bg-muted text-muted-foreground hover:text-foreground',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      {Icon ? <Icon size={22} /> : <span className="text-lg leading-none">{species}</span>}
    </button>
  );
}

function HatPickerItem({
  hatEmoji,
  isSelected,
  disabled,
  onClick,
}: {
  hatEmoji: string;
  isSelected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const HatIcon = HAT_ICON_MAP[hatEmoji];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex items-center justify-center rounded-full p-1.5 transition-all',
        isSelected
          ? 'bg-primary/15 ring-1 ring-primary text-primary'
          : 'hover:bg-muted text-muted-foreground hover:text-foreground',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      {HatIcon ? <HatIcon size={18} /> : <span className="text-lg leading-none">{hatEmoji}</span>}
    </button>
  );
}

export default function CompanionSettings({ open, onOpenChange }: CompanionSettingsProps) {
  const t = useTranslations('companion');
  const user = useAuthStore((s) => s.user);
  const {
    enabled,
    muted,
    nameOverride,
    speciesOverride,
    hatOverride,
    setEnabled,
    setMuted,
    setNameOverride,
    setSpeciesOverride,
    setHatOverride,
  } = useCompanionStore();

  const bones = useMemo(() => {
    if (!user?.id) return null;
    return generateCompanion(user.id);
  }, [user?.id]);

  if (!bones) return null;

  const currentName = nameOverride ?? bones.defaultName;
  const currentSpecies = speciesOverride ?? bones.species;
  const currentHat = hatOverride === undefined ? bones.hat : hatOverride;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('settings')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>{t('enable')}</Label>
              <p className="text-xs text-muted-foreground">{t('enableDesc')}</p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label>{t('mute')}</Label>
              <p className="text-xs text-muted-foreground">{t('muteDesc')}</p>
            </div>
            <Switch checked={muted} onCheckedChange={setMuted} disabled={!enabled} />
          </div>

          <div className="space-y-1">
            <Label>{t('rename')}</Label>
            <Input
              value={currentName}
              onChange={(e) => setNameOverride(e.target.value || null)}
              placeholder={t('renamePlaceholder')}
              maxLength={16}
              disabled={!enabled}
            />
          </div>

          <div className="space-y-1.5">
            <Label>{t('species')}</Label>
            <div className="flex flex-wrap gap-1">
              {SPECIES.map((s) => (
                <SpeciesPickerItem
                  key={s}
                  species={s}
                  isSelected={currentSpecies === s}
                  disabled={!enabled}
                  onClick={() => setSpeciesOverride(s === bones.species ? null : (s as Species))}
                />
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>{t('hat')}</Label>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                onClick={() => setHatOverride(undefined)}
                className={cn(
                  'rounded-full px-2.5 py-1 text-xs transition-all',
                  hatOverride === undefined
                    ? 'bg-primary/15 ring-1 ring-primary text-primary'
                    : 'hover:bg-muted text-muted-foreground',
                )}
                disabled={!enabled}
              >
                {t('defaultHat')}
              </button>
              <button
                type="button"
                onClick={() => setHatOverride(null)}
                className={cn(
                  'rounded-full px-2.5 py-1 text-xs transition-all',
                  currentHat === null && hatOverride !== undefined
                    ? 'bg-primary/15 ring-1 ring-primary text-primary'
                    : 'hover:bg-muted text-muted-foreground',
                )}
                disabled={!enabled}
              >
                {t('noHat')}
              </button>
              {HATS.map((h) => (
                <HatPickerItem
                  key={h}
                  hatEmoji={h}
                  isSelected={currentHat === h}
                  disabled={!enabled}
                  onClick={() => setHatOverride(h as Hat)}
                />
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

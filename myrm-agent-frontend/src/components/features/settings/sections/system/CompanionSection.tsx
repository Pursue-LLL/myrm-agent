'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import {
  evolveStats,
  generateCompanion,
  getTitle,
  HATS,
  RARITIES,
  SPECIES,
} from '@/components/features/companion/companionGenerator';
import { apiRequest } from '@/lib/api';
import useAuthStore from '@/store/useAuthStore';
import useCompanionStore from '@/store/useCompanionStore';

import { IconStar, IconConfetti, IconSparkle } from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';

import type { Hat, Rarity, Species } from '@/components/features/companion/companionGenerator';

const SAVE_DEBOUNCE_MS = 500;
const CELEBRATION_MS = 3000;

interface EvolutionStatusData {
  metrics: { conversations: number; active_days: number; total_messages: number };
  current_rarity: string;
  max_reachable_rarity: string;
  can_evolve: boolean;
  next_threshold: { conversations: number; active_days: number; total_messages: number } | null;
}

function EvolutionProgress({ label, current, target }: { label: string; current: number; target: number }) {
  const pct = Math.min((current / target) * 100, 100);
  const done = current >= target;
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className={done ? 'text-primary font-medium' : 'text-muted-foreground'}>
          {current} / {target}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all ${done ? 'bg-primary' : 'bg-muted-foreground/40'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const CompanionSection = memo(() => {
  const t = useTranslations('companion');
  const userId = useAuthStore((s) => s.user?.id);
  const {
    enabled,
    muted,
    nameOverride,
    speciesOverride,
    hatOverride,
    evolvedRarity,
    evolvedAt,
    setEnabled,
    setMuted,
    setNameOverride,
    setSpeciesOverride,
    setHatOverride,
    evolve,
    loadConfigFromServer,
    saveConfigToServer,
  } = useCompanionStore();

  const bones = useMemo(() => (userId ? generateCompanion(userId) : null), [userId]);

  const [evoStatus, setEvoStatus] = useState<EvolutionStatusData | null>(null);
  const [justEvolved, setJustEvolved] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const effectiveRarity: Rarity = (evolvedRarity ?? bones?.rarity ?? 'Common') as Rarity;
  const effectiveRarityIdx = RARITIES.indexOf(effectiveRarity);
  const isMaxLevel = effectiveRarityIdx >= RARITIES.length - 1;

  useEffect(() => {
    loadConfigFromServer();
  }, [loadConfigFromServer]);

  // Only the user's own edits are written back (coalesced while typing). Saving on mount would overwrite the
  // server copy with local defaults whenever the load is still in flight; a pending edit is flushed on leaving.
  const scheduleSave = useCallback(() => {
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = undefined;
      void saveConfigToServer();
    }, SAVE_DEBOUNCE_MS);
  }, [saveConfigToServer]);

  useEffect(
    () => () => {
      if (saveTimerRef.current !== undefined) {
        clearTimeout(saveTimerRef.current);
        void saveConfigToServer();
      }
    },
    [saveConfigToServer],
  );

  useEffect(() => {
    if (!enabled || !bones || !userId) {
      return;
    }
    let cancelled = false;

    const fetchStatus = async () => {
      try {
        const status = await apiRequest<EvolutionStatusData>(
          `/companion/evolution-status?current_rarity=${effectiveRarity}`,
          { silent: true },
        );
        if (!cancelled) {
          setEvoStatus(status);
        }
      } catch {
        /* non-critical */
      }
    };

    fetchStatus();
    return () => {
      cancelled = true;
    };
  }, [enabled, bones, userId, effectiveRarity, evolvedAt]);

  const handleEvolve = useCallback(() => {
    if (!bones || !userId) {
      return;
    }
    const nextRarity = RARITIES[RARITIES.indexOf(effectiveRarity) + 1];
    const newStats = evolveStats(bones.stats, bones.peakStat, userId, nextRarity);

    evolve(nextRarity, newStats);
    // The status described the previous rarity; until the next one arrives it must not offer another evolution.
    setEvoStatus(null);
    setJustEvolved(true);
    setTimeout(() => setJustEvolved(false), CELEBRATION_MS);
  }, [bones, userId, effectiveRarity, evolve]);

  const changeName = useCallback(
    (value: string | null) => {
      setNameOverride(value);
      scheduleSave();
    },
    [setNameOverride, scheduleSave],
  );
  const changeSpecies = useCallback(
    (value: Species | null) => {
      setSpeciesOverride(value);
      scheduleSave();
    },
    [setSpeciesOverride, scheduleSave],
  );
  const changeHat = useCallback(
    (value: Hat | null | undefined) => {
      setHatOverride(value);
      scheduleSave();
    },
    [setHatOverride, scheduleSave],
  );

  if (!bones) {
    return null;
  }

  const currentName = nameOverride ?? bones.defaultName;
  const currentSpecies = speciesOverride ?? bones.species;
  const currentHat = hatOverride === undefined ? bones.hat : hatOverride;
  const title = getTitle(bones.peakStat, effectiveRarity);

  return (
    <SettingsSection title={t('title')}>
      <div className="space-y-5">
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
            onChange={(e) => changeName(e.target.value || null)}
            placeholder={t('renamePlaceholder')}
            maxLength={16}
            disabled={!enabled}
          />
        </div>

        <div className="space-y-1">
          <Label>{t('species')}</Label>
          <div className="flex flex-wrap gap-1.5">
            {SPECIES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => changeSpecies(s === bones.species ? null : (s as Species))}
                className={`rounded-full p-1 text-lg transition-colors ${
                  currentSpecies === s ? 'bg-primary/15 ring-1 ring-primary' : 'hover:bg-muted'
                }`}
                disabled={!enabled}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <Label>{t('hat')}</Label>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => changeHat(undefined)}
              className={`rounded-full px-2 py-1 text-xs transition-colors ${
                hatOverride === undefined ? 'bg-primary/15 ring-1 ring-primary' : 'hover:bg-muted'
              }`}
              disabled={!enabled}
            >
              {t('defaultHat')}
            </button>
            <button
              type="button"
              onClick={() => changeHat(null)}
              className={`rounded-full px-2 py-1 text-xs transition-colors ${
                currentHat === null && hatOverride !== undefined
                  ? 'bg-primary/15 ring-1 ring-primary'
                  : 'hover:bg-muted'
              }`}
              disabled={!enabled}
            >
              {t('noHat')}
            </button>
            {HATS.map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => changeHat(h as Hat)}
                className={`rounded-full p-1 text-lg transition-colors ${
                  currentHat === h ? 'bg-primary/15 ring-1 ring-primary' : 'hover:bg-muted'
                }`}
                disabled={!enabled}
              >
                {h}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1 rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5">
          <Label>{t('themeFollowWorkspace')}</Label>
          <p className="text-xs text-muted-foreground">{t('themeFollowWorkspaceDesc')}</p>
          <Link href="/settings/preferences" className="inline-flex text-xs font-medium text-primary hover:underline">
            {t('themeFollowWorkspaceLink')}
          </Link>
        </div>

        {/* Evolution section */}
        {enabled && (
          <div className="space-y-3 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between">
              <Label>{t('evolution.title')}</Label>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">{t(`rarity.${effectiveRarity}`)}</span>
                <span className="inline-flex items-center gap-0.5">
                  {Array.from({ length: effectiveRarityIdx + 1 }, (_, i) => (
                    <IconStar key={i} className="w-3.5 h-3.5 text-primary" />
                  ))}
                </span>
              </div>
            </div>

            {title && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">{t('evolution.titleLabel')}:</span>
                <span className="font-medium text-primary">{t(`evolution.titles.${bones.peakStat}`)}</span>
              </div>
            )}

            {justEvolved && (
              <div className="rounded-full bg-primary/10 p-2 text-center text-sm font-medium text-primary animate-in fade-in zoom-in-95">
                <IconConfetti className="inline w-4 h-4 mr-1" />
                {t('evolution.celebrationDesc', {
                  name: currentName,
                  rarity: t(`rarity.${effectiveRarity}`),
                })}
              </div>
            )}

            {isMaxLevel ? (
              <p className="text-xs text-muted-foreground text-center py-1">
                <IconSparkle className="inline w-4 h-4 mr-1" /> {t('evolution.maxLevel')}
              </p>
            ) : evoStatus && (evoStatus.next_threshold || evoStatus.can_evolve) ? (
              <div className="space-y-2">
                {evoStatus.next_threshold && (
                  <>
                    <p className="text-xs text-muted-foreground">{t('evolution.progress')}</p>
                    <EvolutionProgress
                      label={t('evolution.conversations')}
                      current={evoStatus.metrics.conversations}
                      target={evoStatus.next_threshold.conversations}
                    />
                    <EvolutionProgress
                      label={t('evolution.activeDays')}
                      current={evoStatus.metrics.active_days}
                      target={evoStatus.next_threshold.active_days}
                    />
                    <EvolutionProgress
                      label={t('evolution.totalMessages')}
                      current={evoStatus.metrics.total_messages}
                      target={evoStatus.next_threshold.total_messages}
                    />
                  </>
                )}
                {evoStatus.can_evolve && (
                  <Button size="sm" className="w-full" onClick={handleEvolve}>
                    <IconStar className="inline w-4 h-4 mr-1" />
                    {t('evolution.evolveButton')}
                  </Button>
                )}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

CompanionSection.displayName = 'CompanionSection';

export default CompanionSection;

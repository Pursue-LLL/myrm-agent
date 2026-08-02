'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
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
  const user = useAuthStore((s) => s.user);
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

  const bones = useMemo(() => {
    if (!user?.id) return null;
    return generateCompanion(user.id);
  }, [user?.id]);

  const [evoStatus, setEvoStatus] = useState<EvolutionStatusData | null>(null);
  const [evoLoading, setEvoLoading] = useState(false);
  const [justEvolved, setJustEvolved] = useState(false);

  const effectiveRarity: Rarity = (evolvedRarity ?? bones?.rarity ?? 'Common') as Rarity;
  const effectiveRarityIdx = RARITIES.indexOf(effectiveRarity);
  const isMaxLevel = effectiveRarityIdx >= RARITIES.length - 1;

  useEffect(() => {
    loadConfigFromServer();
  }, [loadConfigFromServer]);

  useEffect(() => {
    const timer = setTimeout(() => {
      saveConfigToServer();
    }, 500);
    return () => clearTimeout(timer);
  }, [nameOverride, speciesOverride, hatOverride, saveConfigToServer]);

  useEffect(() => {
    if (!enabled || !bones || !user?.id) return;
    let cancelled = false;

    const fetchStatus = async () => {
      try {
        const resp = await apiRequest<{ data: EvolutionStatusData }>(
          `/companion/evolution-status?current_rarity=${effectiveRarity}`,
        );
        if (!cancelled) setEvoStatus(resp.data);
      } catch {
        /* non-critical */
      }
    };

    fetchStatus();
    return () => {
      cancelled = true;
    };
  }, [enabled, bones, user?.id, effectiveRarity, evolvedAt]);

  const handleEvolve = useCallback(() => {
    if (!evoStatus?.can_evolve || !bones || !user?.id || evoLoading) return;
    setEvoLoading(true);

    const nextRarityIdx = RARITIES.indexOf(effectiveRarity) + 1;
    const nextRarity = RARITIES[nextRarityIdx];
    const newStats = evolveStats(bones.stats, bones.peakStat, user.id, nextRarity);

    evolve(nextRarity, newStats);
    setJustEvolved(true);
    setEvoLoading(false);
    setTimeout(() => setJustEvolved(false), 3000);
  }, [evoStatus, bones, user?.id, evoLoading, effectiveRarity, evolve]);

  if (!bones) return null;

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
            onChange={(e) => setNameOverride(e.target.value || null)}
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
                onClick={() => setSpeciesOverride(s === bones.species ? null : (s as Species))}
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
              onClick={() => setHatOverride(undefined)}
              className={`rounded-full px-2 py-1 text-xs transition-colors ${
                hatOverride === undefined ? 'bg-primary/15 ring-1 ring-primary' : 'hover:bg-muted'
              }`}
              disabled={!enabled}
            >
              {t('defaultHat')}
            </button>
            <button
              type="button"
              onClick={() => setHatOverride(null)}
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
                onClick={() => setHatOverride(h as Hat)}
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
          <Link
            href="/settings/preferences"
            className="inline-flex text-xs font-medium text-primary hover:underline"
          >
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
            ) : evoStatus?.next_threshold ? (
              <div className="space-y-2">
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
                {evoStatus.can_evolve && (
                  <Button size="sm" className="w-full" onClick={handleEvolve} disabled={evoLoading}>
                    {evoLoading ? (
                      '...'
                    ) : (
                      <>
                        <IconStar className="inline w-4 h-4 mr-1" />
                        {t('evolution.evolveButton')}
                      </>
                    )}
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

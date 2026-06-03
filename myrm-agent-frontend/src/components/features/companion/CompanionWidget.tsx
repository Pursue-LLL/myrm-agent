'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/primitives/hover-card';
import { IconHeart, IconSparkle, IconStar } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import useChatStore from '@/store/useChatStore';
import useCompanionStore, { getEffectiveSnacks } from '@/store/useCompanionStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';

import CompanionBubble from './CompanionBubble';
import {
  checkEvolution,
  computeMood,
  evolveStats,
  generateCompanion,
  getObserverLimits,
  getTitle,
  RARITIES,
  STAT_NAMES,
} from './companionGenerator';
import { SPECIES_ICON_MAP } from './CompanionIcons';
import CompanionSettings from './CompanionSettings';
import CompanionSprite from './CompanionSprite';

import type { CompanionBones, CompanionStats, Rarity } from './companionGenerator';

function getHeuristicCategory(snippet: string): 'error' | 'success' | 'general' {
  const lowercase = snippet.toLowerCase();

  // Heuristic Category 1: Error, failures, warnings
  const isError = /error|fail|exception|bug|cannot|unable|warn|invalid|incorrect|报错|失败|无法|异常|错误/.test(
    lowercase,
  );
  if (isError) return 'error';

  // Heuristic Category 2: Success, completion, passes
  const isSuccess = /success|pass|complete|finish|done|resolve|solved|ok|绿|通过|成功|解决|完成/.test(lowercase);
  if (isSuccess) return 'success';

  return 'general';
}

function isBirthdayToday(hatchedAt: number | null): boolean {
  if (!hatchedAt) return false;
  const now = new Date();
  const born = new Date(hatchedAt);
  return (
    now.getMonth() === born.getMonth() && now.getDate() === born.getDate() && now.getFullYear() !== born.getFullYear()
  );
}

function HeartBurst() {
  return (
    <span
      className="pointer-events-none absolute -top-2 left-1/2 -translate-x-1/2 text-sm"
      style={{ animation: 'companion-heart 1s ease-out forwards' }}
    >
      <IconHeart className="inline-block" />
    </span>
  );
}

function ProgressBar({ current, required, label }: { current: number; required: number; label: string }) {
  const pct = Math.min((current / required) * 100, 100);
  return (
    <div className="flex items-center gap-1.5 text-[10px]">
      <span className="w-10 text-muted-foreground truncate">{label}</span>
      <div className="h-1 flex-1 rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary/60 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 text-right font-mono text-muted-foreground">
        {current}/{required}
      </span>
    </div>
  );
}

function SnackButton({ t }: { t: ReturnType<typeof useTranslations<'companion'>> }) {
  const { snacksRemaining, feedSnack } = useCompanionStore();
  const lastReset = useCompanionStore((s) => s.lastSnackReset);
  const remaining = getEffectiveSnacks(snacksRemaining, lastReset);
  const [justFed, setJustFed] = useState(false);
  const feedTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(feedTimerRef.current), []);

  const handleFeed = useCallback(() => {
    const ok = feedSnack();
    if (!ok) return;
    setJustFed(true);
    clearTimeout(feedTimerRef.current);
    feedTimerRef.current = setTimeout(() => setJustFed(false), 1200);
  }, [feedSnack]);

  return (
    <div className="flex items-center justify-between border-t border-border pt-2">
      <div className="flex items-center gap-1.5">
        <div className="flex gap-0.5">
          {Array.from({ length: 3 }, (_, i) => (
            <span
              key={i}
              className={cn(
                'inline-block h-2 w-2 rounded-full transition-all duration-300',
                i < remaining ? 'bg-primary scale-100' : 'bg-muted scale-75',
              )}
            />
          ))}
        </div>
        <span className="text-[10px] text-muted-foreground">
          {remaining > 0 ? t('snack.remaining', { count: remaining }) : t('snack.empty')}
        </span>
      </div>
      <button
        type="button"
        onClick={handleFeed}
        disabled={remaining <= 0}
        className={cn(
          'rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-all duration-200',
          remaining > 0
            ? 'bg-primary/10 text-primary hover:bg-primary/20 active:scale-95'
            : 'cursor-not-allowed bg-muted text-muted-foreground',
          justFed && 'animate-companion-munch',
        )}
      >
        {justFed ? t('snack.xpGain') : t('snack.feed')}
      </button>
    </div>
  );
}

function InfoCard({
  bones,
  userId,
  t,
}: {
  bones: CompanionBones;
  userId: string;
  t: ReturnType<typeof useTranslations<'companion'>>;
}) {
  const { nameOverride, petCount, conversationCount, hatchedAt, evolvedRarity, evolvedStats, evolve } =
    useCompanionStore();
  const [evolving, setEvolving] = useState(false);
  const name = nameOverride ?? bones.defaultName;
  const birthday = isBirthdayToday(hatchedAt);

  const effectiveRarity: Rarity = (evolvedRarity ?? bones.rarity) as Rarity;
  const effectiveStars = RARITIES.indexOf(effectiveRarity) + 1;
  const effectiveStats: CompanionStats = evolvedStats ?? bones.stats;
  const title = getTitle(bones.peakStat, effectiveRarity);

  const evoCheck = useMemo(
    () => checkEvolution(effectiveRarity, petCount, hatchedAt, conversationCount),
    [effectiveRarity, petCount, hatchedAt, conversationCount],
  );

  const handleEvolve = useCallback(() => {
    if (!evoCheck.canEvolve || !evoCheck.nextRarity || evolving) return;
    setEvolving(true);
    const newStats = evolveStats(bones.stats, bones.peakStat, userId, evoCheck.nextRarity);
    evolve(evoCheck.nextRarity, newStats);
    const celebrationName = nameOverride ?? bones.defaultName;
    const nextRarityLabel = t(`rarity.${evoCheck.nextRarity}`);
    setTimeout(() => {
      setEvolving(false);
      useCompanionStore
        .getState()
        .setReaction(t('evolution.celebrationDesc', { name: celebrationName, rarity: nextRarityLabel }));
    }, 1000);
  }, [evoCheck, evolving, bones, userId, evolve, nameOverride, t]);

  const SpeciesIcon = SPECIES_ICON_MAP[bones.species];

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        {SpeciesIcon ? (
          <span className="text-foreground/80">
            <SpeciesIcon size={20} />
          </span>
        ) : (
          <span className="text-lg">{bones.species}</span>
        )}
        <span className="font-semibold">{name}</span>
        {bones.shiny && (
          <span className="text-xs text-yellow-500">
            <IconSparkle />
          </span>
        )}
        {birthday && <span className="text-xs">{t('info.birthday')}</span>}
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{t(`rarity.${effectiveRarity}`)}</span>
        <span>
          {Array.from({ length: effectiveStars }, (_, i) => (
            <IconStar key={i} className="inline-block" />
          ))}
        </span>
      </div>

      {title && <p className="text-xs font-medium text-primary">{t(`evolution.titles.${bones.peakStat}`)}</p>}

      <p className="text-xs italic text-muted-foreground">{bones.personality}</p>

      <div className="space-y-1">
        {STAT_NAMES.map((stat) => (
          <div key={stat} className="flex items-center gap-2 text-xs">
            <span className="w-16 text-muted-foreground">{t(`stats.${stat}`)}</span>
            <div className="h-1.5 flex-1 rounded-full bg-muted">
              <div
                className={cn('h-full rounded-full', stat === bones.peakStat ? 'bg-primary' : 'bg-muted-foreground/40')}
                style={{ width: `${effectiveStats[stat]}%` }}
              />
            </div>
            <span className="w-6 text-right font-mono">{effectiveStats[stat]}</span>
          </div>
        ))}
      </div>

      {evoCheck.progress && (
        <div className="space-y-1 border-t border-border pt-2">
          <p className="text-[10px] font-medium text-muted-foreground">
            {t('evolution.progressTitle', { next: t(`rarity.${evoCheck.nextRarity}`) })}
          </p>
          <ProgressBar
            current={evoCheck.progress.petCount.current}
            required={evoCheck.progress.petCount.required}
            label={t('evolution.pets')}
          />
          <ProgressBar
            current={evoCheck.progress.daysActive.current}
            required={evoCheck.progress.daysActive.required}
            label={t('evolution.days')}
          />
          <ProgressBar
            current={evoCheck.progress.conversationCount.current}
            required={evoCheck.progress.conversationCount.required}
            label={t('evolution.chats')}
          />
          {evoCheck.canEvolve && (
            <button
              type="button"
              onClick={handleEvolve}
              disabled={evolving}
              className={cn(
                'mt-1 w-full rounded-full py-1 text-xs font-medium transition-colors',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                evolving && 'animate-pulse opacity-70',
              )}
            >
              {evolving ? <IconSparkle className="inline-block" /> : t('evolution.evolveButton')}
            </button>
          )}
        </div>
      )}

      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {t('info.petCount')}: {petCount}
        </span>
        {hatchedAt && (
          <span>
            {t('info.hatchedAt')} {new Date(hatchedAt).toLocaleDateString()}
          </span>
        )}
      </div>

      <SnackButton t={t} />
    </div>
  );
}

export default function CompanionWidget() {
  const t = useTranslations('companion');
  const tGoal = useTranslations('Goal');
  const user = useAuthStore((s) => s.user);
  const loading = useChatStore((s) => s.loading);
  const goal = useGoalStore((s) => s.activeGoal);
  const { enabled, muted, speciesOverride, hatOverride, hatchedAt, currentReaction, pet, hatch } = useCompanionStore();

  const [showHeart, setShowHeart] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const prevLoadingRef = useRef(loading);
  const prevGoalStatusRef = useRef(goal?.status);
  const heartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const bones = useMemo(() => {
    if (!user?.id) return null;
    return generateCompanion(user.id);
  }, [user?.id]);

  // Auto-hatch on first render if not hatched
  useEffect(() => {
    if (bones && !hatchedAt && enabled) {
      hatch();
    }
  }, [bones, hatchedAt, enabled, hatch]);

  // Detect loading→false transition for bounce + Observer trigger
  const [animState, setAnimState] = useState<'idle' | 'working' | 'bounce'>('idle');
  useEffect(() => {
    if (loading) {
      setAnimState('working');
      prevLoadingRef.current = true;
      return;
    }
    if (!prevLoadingRef.current) return;
    prevLoadingRef.current = false;

    setAnimState('bounce');
    const timer = setTimeout(() => setAnimState('idle'), 600);

    const abortCtrl = new AbortController();

    const store = useCompanionStore.getState();
    const effRarity: Rarity = (store.evolvedRarity ?? bones?.rarity) as Rarity;
    if (store.canTriggerObserver(effRarity) && bones) {
      store.recordObserverTrigger();
      const messages = useChatStore.getState().messages;
      let lastContent: string | undefined;
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant' && messages[i].content) {
          lastContent = messages[i].content;
          break;
        }
      }
      if (lastContent) {
        const snippet = lastContent.slice(0, 200);
        const category = getHeuristicCategory(snippet);
        const index = Math.floor(Math.random() * 4);
        const reaction = t(`reactions.${bones.peakStat}.${category}.${index}`);
        if (reaction) {
          store.setReaction(reaction);
        }
      }
    }

    return () => {
      clearTimeout(timer);
      abortCtrl.abort();
    };
  }, [loading, bones]);

  // Goal status resonance
  useEffect(() => {
    if (goal?.status === prevGoalStatusRef.current) return;

    const store = useCompanionStore.getState();
    if (goal?.status === 'paused') {
      store.setReaction(tGoal('statusPaused'));
    } else if (goal?.status === 'complete') {
      store.setReaction(tGoal('statusComplete'));
      setAnimState('bounce');
      const timer = setTimeout(() => setAnimState('idle'), 600);
      prevGoalStatusRef.current = goal?.status;
      return () => clearTimeout(timer);
    } else if (goal?.status === 'active' && prevGoalStatusRef.current === 'paused') {
      store.setReaction(tGoal('statusActive'));
    }

    prevGoalStatusRef.current = goal?.status;
  }, [goal?.status, tGoal]);

  // Auto-clear observer reaction after display (duration scales with rarity)
  const evolvedRarity = useCompanionStore((s) => s.evolvedRarity);
  const effectiveRarity: Rarity = useMemo(
    () => (evolvedRarity ?? bones?.rarity ?? 'Common') as Rarity,
    [evolvedRarity, bones?.rarity],
  );

  useEffect(() => {
    if (!currentReaction) return;
    const { displayDurationMs } = getObserverLimits(effectiveRarity);
    const timer = setTimeout(() => useCompanionStore.getState().setReaction(null), displayDurationMs);
    return () => clearTimeout(timer);
  }, [currentReaction, effectiveRarity]);

  // Check if evolution is available and trigger notification bubble
  const evoNotifiedRef = useRef(false);
  useEffect(() => {
    if (!bones || evoNotifiedRef.current) return;
    const store = useCompanionStore.getState();
    const evoRarity = (store.evolvedRarity ?? bones.rarity) as Rarity;
    const evo = checkEvolution(evoRarity, store.petCount, store.hatchedAt, store.conversationCount);
    if (evo.canEvolve && !store.currentReaction && !loading) {
      evoNotifiedRef.current = true;
      store.setReaction(t('evolution.readyNotification'));
    }
  }, [bones, loading, t]);

  // Mood computation — recompute when relevant signals change
  const petCount = useCompanionStore((s) => s.petCount);
  const lastPetAt = useCompanionStore((s) => s.lastPetAt);
  const conversationCount = useCompanionStore((s) => s.conversationCount);
  const lastInteractionAt = useCompanionStore((s) => s.lastInteractionAt);
  const isGoalComplete = goal?.status === 'complete';
  const isEvolutionRecent = useMemo(() => {
    const ea = useCompanionStore.getState().evolvedAt;
    return !!ea && Date.now() - ea < 60_000;
  }, [evolvedRarity]);

  useEffect(() => {
    const store = useCompanionStore.getState();
    const mood = computeMood({
      petCount,
      lastPetAt,
      conversationCount,
      lastInteractionAt: store.lastInteractionAt,
      isGoalComplete,
      isEvolutionRecent,
    });
    store.setMood(mood);
  }, [petCount, lastPetAt, conversationCount, lastInteractionAt, isGoalComplete, isEvolutionRecent]);

  // Touch interaction timestamp on user activity
  useEffect(() => {
    if (loading) {
      useCompanionStore.getState().touchInteraction();
    }
  }, [loading]);

  const bubbleMode = useMemo(() => {
    if (muted) return 'hidden' as const;
    if (loading) return 'thinking' as const;
    if (currentReaction) return 'observer' as const;
    if (animState === 'bounce') return 'completion' as const;
    return 'hidden' as const;
  }, [muted, loading, currentReaction, animState]);

  const handleClick = useCallback(() => {
    pet();
    setShowHeart(true);
    if (heartTimerRef.current) clearTimeout(heartTimerRef.current);
    heartTimerRef.current = setTimeout(() => setShowHeart(false), 1000);
  }, [pet]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setSettingsOpen(true);
  }, []);

  if (!enabled || !bones) return null;

  const birthday = isBirthdayToday(hatchedAt);

  return (
    <div className="relative hidden md:flex flex-col items-center" onContextMenu={handleContextMenu}>
      <CompanionBubble mode={bubbleMode} observerText={currentReaction} effectiveRarity={effectiveRarity} />

      <HoverCard openDelay={300}>
        <HoverCardTrigger asChild>
          <div className="relative">
            <CompanionSprite
              bones={bones}
              animState={animState}
              speciesOverride={speciesOverride}
              hatOverride={hatOverride}
              onClick={handleClick}
              isBirthday={birthday}
            />
            {showHeart && <HeartBurst />}
          </div>
        </HoverCardTrigger>
        <HoverCardContent side="top" className="w-56">
          <InfoCard bones={bones} userId={user!.id} t={t} />
        </HoverCardContent>
      </HoverCard>

      <CompanionSettings open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}

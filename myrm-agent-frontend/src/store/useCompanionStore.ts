/**
 * Companion Store — Zustand state for the pet companion system.
 *
 * Persisted fields (localStorage): enabled, muted, nameOverride, speciesOverride,
 * hatOverride, paletteThemeOverride, hatchedAt, petCount, conversationCount,
 * evolvedRarity, evolvedStats, evolvedAt, snacksRemaining, lastSnackReset.
 *
 * Session-scoped fields (not persisted): currentReaction, lastPetAt, observerCount,
 * lastObserverTrigger, mascotStatus, mood, lastInteractionAt.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { CompanionStats, Hat, Mood, Rarity, Species } from '@/components/features/companion/companionGenerator';
import { getObserverLimits } from '@/components/features/companion/companionGenerator';

import type { SpritesheetMeta } from '@/components/features/companion/sprite/SpriteEngine';

export interface SpriteConfig {
  sheetUrl: string;
  meta?: Partial<SpritesheetMeta>;
  name?: string;
}

const OBSERVER_DEBOUNCE_MS = 3000;
const MAX_DAILY_SNACKS = 3;

function getLocalDateKey(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function getEffectiveSnacks(snacksRemaining: number, lastSnackReset: string | null): number {
  return lastSnackReset === getLocalDateKey() ? snacksRemaining : MAX_DAILY_SNACKS;
}

interface CompanionState {
  // Persisted
  enabled: boolean;
  muted: boolean;
  nameOverride: string | null;
  speciesOverride: Species | null;
  hatOverride: Hat | null | undefined;
  paletteThemeOverride: string | null;
  hatchedAt: number | null;
  petCount: number;
  conversationCount: number;
  evolvedRarity: Rarity | null;
  evolvedStats: CompanionStats | null;
  evolvedAt: number | null;
  snacksRemaining: number;
  lastSnackReset: string | null;

  // Session-scoped (not persisted)
  currentReaction: string | null;
  lastPetAt: number | null;
  observerCount: number;
  lastObserverTrigger: number;
  mascotStatus: string;
  mood: Mood;
  lastInteractionAt: number | null;

  // Mascot XP State
  mascotLevel: number;
  mascotXp: number;
  mascotNextLevelXp: number;
  mascotUnlockedTools: string[];

  // DAG State
  dagData: Record<string, unknown> | null;

  // Sprite overlay state
  spriteEnabled: boolean;
  spriteConfig: SpriteConfig | null;
}

interface CompanionActions {
  setEnabled: (enabled: boolean) => void;
  setMuted: (muted: boolean) => void;
  setNameOverride: (name: string | null) => void;
  setSpeciesOverride: (species: Species | null) => void;
  setHatOverride: (hat: Hat | null | undefined) => void;
  setPaletteThemeOverride: (paletteTheme: string | null) => void;
  setMascotStatus: (status: string) => void;
  setMood: (mood: Mood) => void;
  touchInteraction: () => void;
  setMascotXpState: (state: { level: number; xp: number; next_level_xp: number; unlocked_tools: string[] }) => void;
  setDagData: (data: Record<string, unknown> | null) => void;

  hatch: () => void;
  pet: () => void;
  setReaction: (reaction: string | null) => void;
  incrementConversation: () => void;

  evolve: (rarity: Rarity, stats: CompanionStats) => void;
  feedSnack: () => boolean;

  canTriggerObserver: (effectiveRarity: Rarity) => boolean;
  recordObserverTrigger: () => void;
  resetSession: () => void;
  loadConfigFromServer: () => Promise<void>;
  saveConfigToServer: () => Promise<void>;

  setSpriteEnabled: (enabled: boolean) => void;
  setSpriteConfig: (config: SpriteConfig | null) => void;
}

type CompanionStore = CompanionState & CompanionActions;

const useCompanionStore = create<CompanionStore>()(
  persist(
    (set, get) => ({
      enabled: false,
      muted: false,
      nameOverride: null,
      speciesOverride: null,
      hatOverride: undefined,
      paletteThemeOverride: null,
      hatchedAt: null,
      petCount: 0,
      conversationCount: 0,
      evolvedRarity: null,
      evolvedStats: null,
      evolvedAt: null,
      snacksRemaining: 3,
      lastSnackReset: null,

      currentReaction: null,
      lastPetAt: null,
      observerCount: 0,
      lastObserverTrigger: 0,
      mascotStatus: 'sleeping',
      mood: 'neutral' as Mood,
      lastInteractionAt: null,

      mascotLevel: 1,
      mascotXp: 0,
      mascotNextLevelXp: 100,
      mascotUnlockedTools: [],

      dagData: null,

      spriteEnabled: false,
      spriteConfig: null,

      setEnabled: (enabled) => set({ enabled }),
      setMuted: (muted) => set({ muted }),
      setNameOverride: (name) => set({ nameOverride: name }),
      setSpeciesOverride: (species) => set({ speciesOverride: species }),
      setHatOverride: (hat) => set({ hatOverride: hat }),
      setPaletteThemeOverride: (paletteThemeOverride) => set({ paletteThemeOverride }),
      setMascotStatus: (mascotStatus) => set({ mascotStatus }),
      setMood: (mood) => set({ mood }),
      touchInteraction: () => set({ lastInteractionAt: Date.now() }),
      setMascotXpState: (state) =>
        set({
          mascotLevel: state.level,
          mascotXp: state.xp,
          mascotNextLevelXp: state.next_level_xp,
          mascotUnlockedTools: state.unlocked_tools,
        }),
      setDagData: (dagData) => set({ dagData }),

      hatch: () => {
        if (!get().hatchedAt) {
          set({ hatchedAt: Date.now(), enabled: true });
        }
      },

      pet: () =>
        set((s) => ({
          petCount: s.petCount + 1,
          lastPetAt: Date.now(),
        })),

      setReaction: (reaction) => set({ currentReaction: reaction }),

      incrementConversation: () =>
        set((s) => ({
          conversationCount: s.conversationCount + 1,
        })),

      evolve: (rarity, stats) =>
        set({
          evolvedRarity: rarity,
          evolvedStats: stats,
          evolvedAt: Date.now(),
        }),

      feedSnack: () => {
        const s = get();
        const today = getLocalDateKey();
        const remaining = getEffectiveSnacks(s.snacksRemaining, s.lastSnackReset);
        if (remaining <= 0) return false;
        set({
          snacksRemaining: remaining - 1,
          lastSnackReset: today,
          mascotXp: s.mascotXp + 10,
          mood: 'happy' as Mood,
          lastInteractionAt: Date.now(),
        });
        return true;
      },

      canTriggerObserver: (effectiveRarity: Rarity) => {
        const s = get();
        if (!s.enabled || s.muted) return false;
        const { maxPerSession } = getObserverLimits(effectiveRarity);
        if (s.observerCount >= maxPerSession) return false;
        if (Date.now() - s.lastObserverTrigger < OBSERVER_DEBOUNCE_MS) return false;
        return true;
      },

      recordObserverTrigger: () =>
        set((s) => ({
          observerCount: s.observerCount + 1,
          lastObserverTrigger: Date.now(),
        })),

      resetSession: () =>
        set({
          currentReaction: null,
          lastPetAt: null,
          observerCount: 0,
          lastObserverTrigger: 0,
          mood: 'neutral' as Mood,
          lastInteractionAt: null,
        }),

      loadConfigFromServer: async () => {
        try {
          const { apiRequest } = await import('@/lib/api');
          const data = await apiRequest<{
            value: { name: string | null; species: Species | null; hat: Hat | null; palette_theme: string | null };
          }>('/companion/config');
          if (data && data.value) {
            set({
              nameOverride: data.value.name,
              speciesOverride: data.value.species,
              hatOverride:
                data.value.hat === null ? null : data.value.hat === undefined ? undefined : (data.value.hat as Hat),
              paletteThemeOverride: data.value.palette_theme,
            });
          }
        } catch (e) {
          console.warn('Failed to load companion config from server:', e);
        }
      },

      setSpriteEnabled: (spriteEnabled) => set({ spriteEnabled }),
      setSpriteConfig: (spriteConfig) => set({ spriteConfig }),

      saveConfigToServer: async () => {
        try {
          const { apiRequest } = await import('@/lib/api');
          const state = get();
          await apiRequest('/companion/config', {
            method: 'POST',
            body: JSON.stringify({
              value: {
                name: state.nameOverride,
                species: state.speciesOverride,
                hat: state.hatOverride,
                palette_theme: state.paletteThemeOverride,
              },
              deviceId: 'default_device',
            }),
          });
        } catch (e) {
          console.warn('Failed to save companion config to server:', e);
        }
      },
    }),
    {
      name: 'myrm-companion',
      partialize: (state: CompanionStore) => ({
        enabled: state.enabled,
        muted: state.muted,
        nameOverride: state.nameOverride,
        speciesOverride: state.speciesOverride,
        hatOverride: state.hatOverride,
        paletteThemeOverride: state.paletteThemeOverride,
        hatchedAt: state.hatchedAt,
        petCount: state.petCount,
        conversationCount: state.conversationCount,
        evolvedRarity: state.evolvedRarity,
        evolvedStats: state.evolvedStats,
        evolvedAt: state.evolvedAt,
        snacksRemaining: state.snacksRemaining,
        lastSnackReset: state.lastSnackReset,
        spriteEnabled: state.spriteEnabled,
        spriteConfig: state.spriteConfig,
      }),
    },
  ),
);

export default useCompanionStore;

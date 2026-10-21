/**
 * Companion Store — Zustand state for the pet companion system.
 *
 * Persisted fields (localStorage): enabled, muted, nameOverride, speciesOverride,
 * hatOverride, hatchedAt, petCount, conversationCount,
 * evolvedRarity, evolvedStats, evolvedAt, snacksRemaining, lastSnackReset.
 *
 * Session-scoped fields (not persisted): currentReaction, lastPetAt, observerCount,
 * lastObserverTrigger, mascotStatus, mood, lastInteractionAt, petPaletteOpen,
 * doctorExpandPending.
 *
 * Accent colors follow workspace Theme Profile CSS tokens (see companionTheme.ts).
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { CompanionStats, Hat, Mood, Rarity, Species } from '@/components/features/companion/companionGenerator';
import { getObserverLimits } from '@/components/features/companion/companionGenerator';

import type { CompanionSpriteConfig } from '@/services/companion/petSpritesheet';

export type SpriteConfig = CompanionSpriteConfig;

const OBSERVER_DEBOUNCE_MS = 3000;
const MAX_DAILY_SNACKS = 3;

function getLocalDateKey(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function getEffectiveSnacks(snacksRemaining: number, lastSnackReset: string | null): number {
  return lastSnackReset === getLocalDateKey() ? snacksRemaining : MAX_DAILY_SNACKS;
}

export function sanitizePersistedSpriteState(
  spriteConfig: unknown,
  spriteEnabled: boolean,
): { spriteConfig: SpriteConfig | null; spriteEnabled: boolean } {
  if (!spriteConfig || typeof spriteConfig !== 'object') {
    return { spriteConfig: null, spriteEnabled: false };
  }
  const record = spriteConfig as Record<string, unknown>;
  const petSlug = record.petSlug;
  if (typeof petSlug !== 'string' || !petSlug.trim()) {
    return { spriteConfig: null, spriteEnabled: false };
  }
  return {
    spriteConfig: {
      petSlug: petSlug.trim(),
      displayName: typeof record.displayName === 'string' ? record.displayName : undefined,
      contentSha256: typeof record.contentSha256 === 'string' ? record.contentSha256 : undefined,
    },
    spriteEnabled: spriteEnabled && petSlug.trim().length > 0,
  };
}

interface CompanionState {
  // Persisted
  enabled: boolean;
  muted: boolean;
  nameOverride: string | null;
  speciesOverride: Species | null;
  hatOverride: Hat | null | undefined;
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

  // Session-scoped UI (not persisted)
  petPaletteOpen: boolean;
  doctorExpandPending: boolean;
}

interface CompanionActions {
  setEnabled: (enabled: boolean) => void;
  setMuted: (muted: boolean) => void;
  setNameOverride: (name: string | null) => void;
  setSpeciesOverride: (species: Species | null) => void;
  setHatOverride: (hat: Hat | null | undefined) => void;
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
  setPetPaletteOpen: (open: boolean) => void;
  openCompanionHealthCheck: () => void;
  clearDoctorExpandPending: () => void;
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
      petPaletteOpen: false,
      doctorExpandPending: false,

      setEnabled: (enabled) => set({ enabled }),
      setMuted: (muted) => set({ muted }),
      setNameOverride: (name) => set({ nameOverride: name }),
      setSpeciesOverride: (species) => set({ speciesOverride: species }),
      setHatOverride: (hat) => set({ hatOverride: hat }),
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
        if (remaining <= 0) {
          return false;
        }
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
        if (!s.enabled || s.muted) {
          return false;
        }
        const { maxPerSession } = getObserverLimits(effectiveRarity);
        if (s.observerCount >= maxPerSession) {
          return false;
        }
        if (Date.now() - s.lastObserverTrigger < OBSERVER_DEBOUNCE_MS) {
          return false;
        }
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
            value: {
              name: string | null;
              species: Species | null;
              hat: Hat | null;
              sprite: {
                pet_slug?: string | null;
                content_sha256?: string | null;
                display_name?: string | null;
              } | null;
            };
          }>('/companion/config');
          if (data && data.value) {
            const patch: Partial<CompanionState> = {
              nameOverride: data.value.name,
              speciesOverride: data.value.species,
              hatOverride:
                data.value.hat === null ? null : data.value.hat === undefined ? undefined : (data.value.hat as Hat),
            };
            const slug = data.value.sprite?.pet_slug;
            if (slug) {
              patch.spriteConfig = {
                petSlug: slug,
                contentSha256: data.value.sprite?.content_sha256 ?? undefined,
                displayName: data.value.sprite?.display_name ?? undefined,
              };
              patch.spriteEnabled = true;
            } else {
              patch.spriteConfig = null;
            }
            set(patch);
          }
        } catch (e) {
          console.warn('Failed to load companion config from server:', e);
        }
      },

      setSpriteEnabled: (spriteEnabled) => set({ spriteEnabled }),
      setSpriteConfig: (spriteConfig) => set({ spriteConfig }),
      setPetPaletteOpen: (petPaletteOpen) => set({ petPaletteOpen }),

      openCompanionHealthCheck: () =>
        set({
          petPaletteOpen: true,
          doctorExpandPending: true,
        }),

      clearDoctorExpandPending: () => set({ doctorExpandPending: false }),

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
                sprite: state.spriteConfig
                  ? {
                      pet_slug: state.spriteConfig.petSlug,
                      content_sha256: state.spriteConfig.contentSha256 ?? null,
                      display_name: state.spriteConfig.displayName ?? null,
                    }
                  : null,
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
      onRehydrateStorage: () => (state) => {
        if (!state) {
          return;
        }
        const sanitized = sanitizePersistedSpriteState(state.spriteConfig, state.spriteEnabled);
        state.spriteConfig = sanitized.spriteConfig;
        state.spriteEnabled = sanitized.spriteEnabled;
      },
    },
  ),
);

export default useCompanionStore;

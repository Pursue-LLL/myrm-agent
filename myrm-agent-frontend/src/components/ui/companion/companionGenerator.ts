/**
 * Companion Generator — deterministic pet generation from userId.
 *
 * Uses Mulberry32 PRNG seeded with FNV-1a hash of (userId + salt).
 * Bones (species, rarity, stats, hat, shiny, name) are computed on every read,
 * never stored, so localStorage edits cannot forge rarity.
 */

// ---------------------------------------------------------------------------
// PRNG: Mulberry32 (same algorithm as Claude Code buddy/companion.ts)
// ---------------------------------------------------------------------------

function mulberry32(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 0x100000000;
  };
}

// ---------------------------------------------------------------------------
// Hash: FNV-1a 32-bit
// ---------------------------------------------------------------------------

const FNV_OFFSET = 0x811c9dc5;
const FNV_PRIME = 0x01000193;
const SALT = 'myrm-companion-v1';

function fnv1a(input: string): number {
  let hash = FNV_OFFSET;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, FNV_PRIME);
  }
  return hash >>> 0;
}

// ---------------------------------------------------------------------------
// Data tables
// ---------------------------------------------------------------------------

export const SPECIES = [
  '🐱',
  '🐶',
  '🐻',
  '🐰',
  '🦉',
  '🐲',
  '🦥',
  '🐧',
  '🦊',
  '🐙',
  '🌵',
  '🤖',
  '🍄',
  '🐼',
  '🐸',
] as const;

export type Species = (typeof SPECIES)[number];

export const RARITIES = ['Common', 'Uncommon', 'Rare', 'Epic', 'Legendary'] as const;
export type Rarity = (typeof RARITIES)[number];

const RARITY_WEIGHTS: readonly number[] = [60, 25, 10, 4, 1];
const RARITY_FLOORS: Record<Rarity, number> = {
  Common: 5,
  Uncommon: 15,
  Rare: 25,
  Epic: 35,
  Legendary: 50,
};

export const STAT_NAMES = ['debugging', 'patience', 'chaos', 'wisdom', 'snark'] as const;
export type StatName = (typeof STAT_NAMES)[number];

export const HATS = ['👑', '🎩', '⭐', '🧙', '🎀', '🌸', '🔥', '❄️', '🎓'] as const;
export type Hat = (typeof HATS)[number] | null;

const PRESET_NAMES_EN = [
  'Pip',
  'Nyx',
  'Boo',
  'Mochi',
  'Kiki',
  'Ozzy',
  'Sage',
  'Nova',
  'Fizz',
  'Rune',
  'Tofu',
  'Pixel',
  'Bean',
  'Echo',
  'Coco',
  'Spark',
  'Miso',
  'Bolt',
  'Luna',
  'Chip',
  'Taro',
  'Fern',
  'Oreo',
  'Puff',
  'Jinx',
  'Dusk',
  'Reef',
  'Wren',
  'Gizmo',
  'Plum',
  'Flint',
  'Ash',
  'Bloom',
  'Haze',
  'Snip',
  'Volt',
  'Drift',
  'Moss',
  'Clover',
  'Byte',
  'Lark',
  'Opal',
  'Zest',
  'Cinder',
  'Quill',
  'Mica',
  'Thistle',
  'Ember',
];

// Personality keywords per stat
const STAT_PEAK_TRAITS: Record<StatName, string> = {
  debugging: 'analytical',
  patience: 'calm',
  chaos: 'chaotic',
  wisdom: 'wise',
  snark: 'snarky',
};

const STAT_DUMP_TRAITS: Record<StatName, string> = {
  debugging: 'oblivious',
  patience: 'impatient',
  chaos: 'orderly',
  wisdom: 'naive',
  snark: 'earnest',
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CompanionStats {
  debugging: number;
  patience: number;
  chaos: number;
  wisdom: number;
  snark: number;
}

export interface CompanionBones {
  species: Species;
  rarity: Rarity;
  stars: number;
  stats: CompanionStats;
  peakStat: StatName;
  dumpStat: StatName;
  shiny: boolean;
  hat: Hat;
  defaultName: string;
  personality: string;
}

// ---------------------------------------------------------------------------
// Roll functions
// ---------------------------------------------------------------------------

function rollRarity(rand: () => number): Rarity {
  const totalWeight = RARITY_WEIGHTS.reduce((a, b) => a + b, 0);
  let roll = rand() * totalWeight;
  for (let i = 0; i < RARITIES.length; i++) {
    roll -= RARITY_WEIGHTS[i];
    if (roll <= 0) return RARITIES[i];
  }
  return RARITIES[0];
}

function rollStats(
  rand: () => number,
  rarity: Rarity,
): {
  stats: CompanionStats;
  peakStat: StatName;
  dumpStat: StatName;
} {
  const floor = RARITY_FLOORS[rarity];
  const indices = STAT_NAMES.map((_, i) => i);

  // Shuffle to pick peak and dump
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }

  const peakIdx = indices[0];
  const dumpIdx = indices[1];

  const values: number[] = STAT_NAMES.map((_, i) => {
    if (i === peakIdx) return Math.min(floor + 50 + Math.floor(rand() * 20), 100);
    if (i === dumpIdx) return Math.max(floor - 10, 1);
    return floor + Math.floor(rand() * (80 - floor));
  });

  const stats: CompanionStats = {
    debugging: values[0],
    patience: values[1],
    chaos: values[2],
    wisdom: values[3],
    snark: values[4],
  };

  return {
    stats,
    peakStat: STAT_NAMES[peakIdx],
    dumpStat: STAT_NAMES[dumpIdx],
  };
}

function rollHat(rand: () => number, rarity: Rarity): Hat {
  if (rarity === 'Common') return null;
  return HATS[Math.floor(rand() * HATS.length)];
}

function rarityToStars(rarity: Rarity): number {
  return RARITIES.indexOf(rarity) + 1;
}

function buildPersonality(peakStat: StatName, dumpStat: StatName): string {
  return `${STAT_PEAK_TRAITS[peakStat]} but ${STAT_DUMP_TRAITS[dumpStat]}`;
}

// ---------------------------------------------------------------------------
// Evolution: deterministic stat boost & titles
// ---------------------------------------------------------------------------

const EVOLVE_BOOST_RANGE = { min: 5, max: 15, peakBonus: 5 };

const STAT_TITLES_EN: Record<StatName, string> = {
  debugging: 'The Analytical',
  patience: 'The Serene',
  chaos: 'The Chaotic',
  wisdom: 'The Sage',
  snark: 'The Sharp',
};

const STAT_TITLES_ZH: Record<StatName, string> = {
  debugging: '分析大师',
  patience: '宁静之心',
  chaos: '混沌使者',
  wisdom: '智慧贤者',
  snark: '毒舌达人',
};

/**
 * Compute evolved stats for a given target rarity.
 * Deterministic: seeded by userId + target rarity.
 * Applies cumulative boosts from each rarity tier up to targetRarity.
 */
export function evolveStats(
  baseStats: CompanionStats,
  peakStat: StatName,
  userId: string,
  targetRarity: Rarity,
): CompanionStats {
  const targetIdx = RARITIES.indexOf(targetRarity);
  const result = { ...baseStats };

  for (let tier = 1; tier <= targetIdx; tier++) {
    const tierRarity = RARITIES[tier];
    const seed = fnv1a(userId + SALT + '-evolve-' + tierRarity);
    const rand = mulberry32(seed);
    const { min, max, peakBonus } = EVOLVE_BOOST_RANGE;

    for (const stat of STAT_NAMES) {
      const boost = min + Math.floor(rand() * (max - min + 1));
      const extra = stat === peakStat ? peakBonus : 0;
      result[stat] = Math.min(result[stat] + boost + extra, 100);
    }
  }

  return result;
}

/**
 * Get the companion's title based on peak stat and rarity.
 * Only Uncommon+ companions receive a title.
 */
export function getTitle(peakStat: StatName, rarity: Rarity, locale: 'en' | 'zh' = 'en'): string | null {
  if (rarity === 'Common') return null;
  return locale === 'zh' ? STAT_TITLES_ZH[peakStat] : STAT_TITLES_EN[peakStat];
}

// ---------------------------------------------------------------------------
// Rarity Abilities — unlocked capabilities per rarity tier
// ---------------------------------------------------------------------------

export interface RarityAbilities {
  title: boolean;
  enhancedPersonality: boolean;
  observerBoost: boolean;
  legendaryFlair: boolean;
}

export function getRarityAbilities(rarity: Rarity): RarityAbilities {
  const level = RARITIES.indexOf(rarity);
  return {
    title: level >= 1,
    enhancedPersonality: level >= 2,
    observerBoost: level >= 3,
    legendaryFlair: level >= 4,
  };
}

const OBSERVER_LIMITS: Record<Rarity, { maxPerSession: number; displayDurationMs: number }> = {
  Common: { maxPerSession: 5, displayDurationMs: 10_000 },
  Uncommon: { maxPerSession: 7, displayDurationMs: 12_000 },
  Rare: { maxPerSession: 9, displayDurationMs: 14_000 },
  Epic: { maxPerSession: 12, displayDurationMs: 16_000 },
  Legendary: { maxPerSession: 15, displayDurationMs: 20_000 },
};

export function getObserverLimits(rarity: Rarity) {
  return OBSERVER_LIMITS[rarity];
}

// ---------------------------------------------------------------------------
// Enhanced Personality — richer prompt injection for Rare+
// ---------------------------------------------------------------------------

const STAT_SECONDARY_TRAITS: Record<StatName, string> = {
  debugging: 'methodical and detail-oriented',
  patience: 'patient and thoughtful',
  chaos: 'unpredictable and creative',
  wisdom: 'insightful and reflective',
  snark: 'witty and sharp-tongued',
};

/**
 * Build enhanced personality description based on rarity.
 * Common/Uncommon: single trait. Rare+: dual traits. Epic+: intensified. Legendary: special marker.
 */
export function getEnhancedPersonality(bones: CompanionBones, effectiveRarity: Rarity): string {
  const abilities = getRarityAbilities(effectiveRarity);
  const baseTrait = STAT_PEAK_TRAITS[bones.peakStat];

  if (!abilities.enhancedPersonality) {
    return baseTrait;
  }

  const sortedStats = STAT_NAMES.map((name) => ({ name, value: bones.stats[name] })).sort((a, b) => b.value - a.value);
  const secondStat = sortedStats.find((s) => s.name !== bones.peakStat);
  const secondTrait = secondStat ? STAT_SECONDARY_TRAITS[secondStat.name] : '';

  if (abilities.legendaryFlair) {
    return `deeply ${baseTrait} and remarkably ${secondTrait}, occasionally offering profound insights`;
  }
  if (abilities.observerBoost) {
    return `deeply ${baseTrait} and remarkably ${secondTrait}`;
  }
  return `${baseTrait} and also ${secondTrait}`;
}

// ---------------------------------------------------------------------------
// Evolution Conditions — multi-dimensional requirements
// ---------------------------------------------------------------------------

export interface EvolutionRequirement {
  petCount: number;
  daysActive: number;
  conversationCount: number;
}

export const EVOLUTION_REQUIREMENTS: Record<Rarity, EvolutionRequirement | null> = {
  Common: { petCount: 20, daysActive: 3, conversationCount: 10 },
  Uncommon: { petCount: 50, daysActive: 14, conversationCount: 30 },
  Rare: { petCount: 100, daysActive: 30, conversationCount: 60 },
  Epic: { petCount: 200, daysActive: 60, conversationCount: 100 },
  Legendary: null,
};

export interface EvolutionCheck {
  canEvolve: boolean;
  currentRarity: Rarity;
  nextRarity: Rarity | null;
  progress: {
    petCount: { current: number; required: number };
    daysActive: { current: number; required: number };
    conversationCount: { current: number; required: number };
  } | null;
}

export function checkEvolution(
  currentRarity: Rarity,
  petCount: number,
  hatchedAt: number | null,
  conversationCount: number,
): EvolutionCheck {
  const currentIdx = RARITIES.indexOf(currentRarity);
  const nextRarity = currentIdx < RARITIES.length - 1 ? RARITIES[currentIdx + 1] : null;
  const req = EVOLUTION_REQUIREMENTS[currentRarity];

  if (!req || !nextRarity) {
    return { canEvolve: false, currentRarity, nextRarity: null, progress: null };
  }

  const daysActive = hatchedAt ? Math.floor((Date.now() - hatchedAt) / (24 * 60 * 60 * 1000)) : 0;

  const canEvolve =
    petCount >= req.petCount && daysActive >= req.daysActive && conversationCount >= req.conversationCount;

  return {
    canEvolve,
    currentRarity,
    nextRarity,
    progress: {
      petCount: { current: petCount, required: req.petCount },
      daysActive: { current: daysActive, required: req.daysActive },
      conversationCount: { current: conversationCount, required: req.conversationCount },
    },
  };
}

// ---------------------------------------------------------------------------
// Mood — positive-only emotion system (no decay penalties)
// ---------------------------------------------------------------------------

export const MOODS = ['neutral', 'happy', 'curious', 'excited', 'sleepy'] as const;
export type Mood = (typeof MOODS)[number];

const MOOD_IDLE_THRESHOLD_MS = 30 * 60 * 1000;
const MOOD_HAPPY_PET_THRESHOLD = 3;
const MOOD_CURIOUS_CONVERSATION_THRESHOLD = 5;

export interface MoodInput {
  petCount: number;
  lastPetAt: number | null;
  conversationCount: number;
  lastInteractionAt: number | null;
  isGoalComplete: boolean;
  isEvolutionRecent: boolean;
}

/**
 * Compute companion mood from usage signals.
 * Positive-only: no punishment for inactivity, just returns to neutral/sleepy.
 */
export function computeMood(input: MoodInput): Mood {
  const now = Date.now();

  if (input.isGoalComplete || input.isEvolutionRecent) return 'excited';

  const recentPet = input.lastPetAt && now - input.lastPetAt < 5 * 60 * 1000;
  if (recentPet && input.petCount >= MOOD_HAPPY_PET_THRESHOLD) return 'happy';

  if (input.conversationCount >= MOOD_CURIOUS_CONVERSATION_THRESHOLD) return 'curious';

  const idle = !input.lastInteractionAt || now - input.lastInteractionAt > MOOD_IDLE_THRESHOLD_MS;
  if (idle) return 'sleepy';

  return 'neutral';
}

// ---------------------------------------------------------------------------
// Main generator (pure function, deterministic)
// ---------------------------------------------------------------------------

let cachedUserId: string | null = null;
let cachedBones: CompanionBones | null = null;

export function generateCompanion(userId: string): CompanionBones {
  if (cachedUserId === userId && cachedBones) return cachedBones;

  const hash = fnv1a(userId + SALT);
  const rand = mulberry32(hash);

  const species = SPECIES[Math.floor(rand() * SPECIES.length)];
  const rarity = rollRarity(rand);
  const { stats, peakStat, dumpStat } = rollStats(rand, rarity);
  const shiny = rand() < 0.01;
  const hat = rollHat(rand, rarity);
  const defaultName = PRESET_NAMES_EN[Math.floor(rand() * PRESET_NAMES_EN.length)];
  const personality = buildPersonality(peakStat, dumpStat);

  cachedBones = {
    species,
    rarity,
    stars: rarityToStars(rarity),
    stats,
    peakStat,
    dumpStat,
    shiny,
    hat,
    defaultName,
    personality,
  };
  cachedUserId = userId;

  return cachedBones;
}

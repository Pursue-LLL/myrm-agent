/**
 * Companion Visual Asset Registry
 *
 * Maps each species to its metadata (label for accessibility).
 * SVG icons are rendered via CompanionIcons.tsx; this module provides
 * label/metadata lookup used by Settings and other UI components.
 */

const SPECIES_LABELS: Record<string, string> = {
  '🐱': 'Cat',
  '🐶': 'Dog',
  '🐻': 'Bear',
  '🐰': 'Rabbit',
  '🦉': 'Owl',
  '🐲': 'Dragon',
  '🦥': 'Sloth',
  '🐧': 'Penguin',
  '🦊': 'Fox',
  '🐙': 'Octopus',
  '🌵': 'Cactus',
  '🤖': 'Robot',
  '🍄': 'Mushroom',
  '🐼': 'Panda',
  '🐸': 'Frog',
};

export interface SpeciesAsset {
  emoji: string;
  label: string;
}

export function getSpeciesAsset(species: string): SpeciesAsset {
  const label = SPECIES_LABELS[species];
  if (label) return { emoji: species, label };
  return { emoji: species, label: 'Custom' };
}

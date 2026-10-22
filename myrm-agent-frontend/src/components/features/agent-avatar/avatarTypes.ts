/**
 * Domain types for Agent Avatar Generation and Dice Lock.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure domain types for deterministic SVG avatars, styles, color presets, and lock states.
 * [POS] src/components/features/agent-avatar/avatarTypes.ts
 */

export type AvatarStyle = 'cyberpunk' | 'pixel' | 'bauhaus' | 'beam';

export interface AvatarMetadata {
  seed: string;
  style: AvatarStyle;
  backgroundColor: string;
  isLocked: boolean;
  svgData: string;
  imageUrl?: string | null;
}

export const AVATAR_COLOR_PRESETS: string[] = [
  '#6366f1', // Indigo
  '#8b5cf6', // Violet
  '#ec4899', // Pink
  '#f43f5e', // Rose
  '#06b6d4', // Cyan
  '#10b981', // Emerald
  '#f59e0b', // Amber
  '#0f172a', // Slate Dark
];

export interface GenerateSvgRequest {
  seed: string;
  style?: AvatarStyle;
  backgroundColor?: string;
}

export interface GenerateAiAvatarRequest {
  prompt: string;
  style?: string;
}

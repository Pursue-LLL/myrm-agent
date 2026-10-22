/**
 * Deterministic SVG Avatar Generator for Bot Mode Multi-Agent Swarms.
 * Generates stable theme colors and geometric SVGs from agent seed strings.
 */

export const AVATAR_PALETTE: readonly string[] = [
  '#6366f1', // Indigo
  '#3b82f6', // Blue
  '#10b981', // Emerald
  '#f59e0b', // Amber
  '#ec4899', // Pink
  '#8b5cf6', // Purple
  '#06b6d4', // Cyan
  '#14b8a6', // Teal
] as const;

export function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

export function getDeterministicColor(seed: string): string {
  const hash = hashString(seed);
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

export function generateDeterministicSvgAvatar(seed: string, size = 32): string {
  const color = getDeterministicColor(seed);
  const initials = seed.slice(0, 2).toUpperCase() || 'AG';
  const radius = size / 2;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <rect width="${size}" height="${size}" rx="${radius}" fill="${color}" />
    <text x="50%" y="54%" font-family="system-ui, sans-serif" font-size="${Math.floor(size * 0.44)}" font-weight="600" fill="#ffffff" dominant-baseline="middle" text-anchor="middle">
      ${initials}
    </text>
  </svg>`;
}

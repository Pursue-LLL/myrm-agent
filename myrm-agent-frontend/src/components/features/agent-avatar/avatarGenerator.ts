/**
 * Pure client-side deterministic SVG avatar generator based on seed algorithms.
 *
 * [INPUT] seed: string, style: AvatarStyle, bgColor: string
 * [OUTPUT] generateDeterministicSvg: zero-network, sub-millisecond SVG markup generator.
 * [POS] src/components/features/agent-avatar/avatarGenerator.ts
 */

import type { AvatarStyle } from './avatarTypes';

/** Simple deterministic hash algorithm (FNV-1a 32-bit derivative) */
function hashSeed(seed: string): number[] {
  let h1 = 2166136261;
  let h2 = 1845123987;
  let h3 = 3012984123;
  let h4 = 4012891231;

  for (let i = 0; i < seed.length; i++) {
    const code = seed.charCodeAt(i);
    h1 = (h1 ^ code) * 16777619;
    h2 = (h2 ^ (code + i)) * 1099511627;
    h3 = (h3 ^ (code * 31)) * 314159265;
    h4 = (h4 ^ (code * 17)) * 271828182;
  }

  return [Math.abs(h1), Math.abs(h2), Math.abs(h3), Math.abs(h4)];
}

export function generateDeterministicSvg(
  seed: string,
  style: AvatarStyle = 'beam',
  bgColor = '#6366f1',
): string {
  const safeSeed = seed.trim() || 'default-agent-avatar';
  const [n1, n2, n3, n4] = hashSeed(safeSeed);
  const safeBg = /^#[0-9a-fA-F]{6}$/.test(bgColor) ? bgColor : '#4f46e5';

  if (style === 'pixel') {
    const rects: string[] = [];
    const palette = ['#ffffff', '#38bdf8', '#818cf8', '#f472b6', '#fbbf24'];
    const accent = palette[n1 % palette.length];

    for (let row = 0; row < 5; row++) {
      for (let col = 0; col < 3; col++) {
        const bit = (n2 >> (row * 3 + col)) & 1;
        if (bit === 1) {
          const fill = (row + col) % 2 === 0 ? accent : '#ffffff';
          rects.push(
            `<rect x="${col * 16 + 10}" y="${row * 16 + 10}" width="14" height="14" rx="2" fill="${fill}" />`,
          );
          if (col < 2) {
            const symCol = 4 - col;
            rects.push(
              `<rect x="${symCol * 16 + 10}" y="${row * 16 + 10}" width="14" height="14" rx="2" fill="${fill}" />`,
            );
          }
        }
      }
    }

    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">` +
      `<rect width="100" height="100" rx="24" fill="${safeBg}" />` +
      rects.join('') +
      `</svg>`
    );
  }

  if (style === 'cyberpunk') {
    const r1 = (n1 % 25) + 15;
    const r2 = (n2 % 20) + 10;
    const x1 = (n3 % 40) + 30;
    const y1 = (n4 % 40) + 30;

    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">` +
      `<defs>` +
      `<linearGradient id="cyber-grad" x1="0%" y1="0%" x2="100%" y2="100%">` +
      `<stop offset="0%" stop-color="#06b6d4" />` +
      `<stop offset="100%" stop-color="#d946ef" />` +
      `</linearGradient>` +
      `</defs>` +
      `<rect width="100" height="100" rx="24" fill="${safeBg}" />` +
      `<circle cx="${x1}" cy="${y1}" r="${r1}" fill="url(#cyber-grad)" opacity="0.85" />` +
      `<polygon points="50,20 ${80 - (n1 % 15)},80 ${20 + (n2 % 15)},80" fill="#facc15" opacity="0.75" />` +
      `<circle cx="50" cy="50" r="${r2}" fill="#ffffff" opacity="0.9" />` +
      `</svg>`
    );
  }

  if (style === 'bauhaus') {
    const cx = (n1 % 30) + 35;
    const cy = (n2 % 30) + 35;
    const rot = n3 % 360;

    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">` +
      `<rect width="100" height="100" rx="24" fill="${safeBg}" />` +
      `<rect x="25" y="25" width="50" height="50" fill="#f43f5e" transform="rotate(${rot} 50 50)" opacity="0.8" />` +
      `<circle cx="${cx}" cy="${cy}" r="22" fill="#3b82f6" opacity="0.85" />` +
      `<line x1="15" y1="50" x2="85" y2="50" stroke="#fbbf24" stroke-width="6" stroke-linecap="round" />` +
      `</svg>`
    );
  }

  // Default: Beam style
  const eyeY = 42 + (n1 % 6);
  const mouthY = 66 + (n2 % 6);
  const glowX = (n3 % 30) + 35;
  const glowY = (n4 % 30) + 35;

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">` +
    `<defs>` +
    `<radialGradient id="beam-glow" cx="50%" cy="50%" r="50%">` +
    `<stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />` +
    `<stop offset="100%" stop-color="${safeBg}" stop-opacity="0.2" />` +
    `</radialGradient>` +
    `</defs>` +
    `<rect width="100" height="100" rx="24" fill="${safeBg}" />` +
    `<circle cx="${glowX}" cy="${glowY}" r="34" fill="url(#beam-glow)" />` +
    `<circle cx="36" cy="${eyeY}" r="4" fill="#ffffff" />` +
    `<circle cx="64" cy="${eyeY}" r="4" fill="#ffffff" />` +
    `<path d="M 40 ${mouthY} Q 50 ${mouthY + 8} 60 ${mouthY}" stroke="#ffffff" stroke-width="3" fill="none" stroke-linecap="round" />` +
    `</svg>`
  );
}

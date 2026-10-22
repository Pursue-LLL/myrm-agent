/**
 * Unit tests for deterministic SVG avatar generator.
 *
 * [INPUT] generateDeterministicSvg, AvatarStyle
 * [OUTPUT] Full coverage for 4 visual styles, seed determinism, and fallback handling.
 * [POS] src/components/features/agent-avatar/__tests__/avatarGenerator.test.ts
 */

import { describe, it, expect } from 'vitest';
import { generateDeterministicSvg } from '../avatarGenerator';
import type { AvatarStyle } from '../avatarTypes';

describe('avatarGenerator - generateDeterministicSvg', () => {
  it('should generate valid SVG markup for default beam style', () => {
    const svg = generateDeterministicSvg('agent-007', 'beam', '#6366f1');
    expect(svg).toContain('<svg xmlns="http://www.w3.org/2000/svg"');
    expect(svg).toContain('viewBox="0 0 100 100"');
    expect(svg).toContain('fill="#6366f1"');
    expect(svg).toContain('</svg>');
  });

  it('should be deterministic: same seed and params produce identical SVG', () => {
    const svg1 = generateDeterministicSvg('alpha-seed-42', 'pixel', '#10b981');
    const svg2 = generateDeterministicSvg('alpha-seed-42', 'pixel', '#10b981');
    expect(svg1).toBe(svg2);
  });

  it('should produce different SVGs for different seeds', () => {
    const svg1 = generateDeterministicSvg('seed-alpha', 'beam', '#6366f1');
    const svg2 = generateDeterministicSvg('seed-beta', 'beam', '#6366f1');
    expect(svg1).not.toBe(svg2);
  });

  it('should generate pixel style with grid rect elements', () => {
    const svg = generateDeterministicSvg('pixel-agent', 'pixel', '#0f172a');
    expect(svg).toContain('<rect');
    expect(svg).toContain('rx="2"');
  });

  it('should generate cyberpunk style with linear gradient and geometric shapes', () => {
    const svg = generateDeterministicSvg('cyber-agent', 'cyberpunk', '#8b5cf6');
    expect(svg).toContain('linearGradient id="cyber-grad"');
    expect(svg).toContain('<polygon');
    expect(svg).toContain('<circle');
  });

  it('should generate bauhaus style with rotated elements and lines', () => {
    const svg = generateDeterministicSvg('bauhaus-agent', 'bauhaus', '#ec4899');
    expect(svg).toContain('transform="rotate(');
    expect(svg).toContain('<line');
  });

  it('should handle empty or whitespace seed gracefully with fallback', () => {
    const svg = generateDeterministicSvg('   ', 'beam', '#6366f1');
    expect(svg).toContain('<svg');
    expect(svg).toContain('</svg>');
  });

  it('should sanitize invalid hex color to safe fallback', () => {
    const svg = generateDeterministicSvg('agent-test', 'beam', 'invalid-color');
    expect(svg).toContain('fill="#4f46e5"');
  });
});

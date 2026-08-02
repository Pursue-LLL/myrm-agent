import { describe, expect, it, beforeEach } from 'vitest';

import {
  resolveCompanionBubbleTone,
  resolveCompanionRarityVisual,
} from '@/services/companion/companionTheme';

describe('companionTheme', () => {
  beforeEach(() => {
    document.documentElement.style.setProperty('--primary', '#588e95');
    document.documentElement.style.setProperty('--primary-hover', '#4a7d84');
    document.documentElement.style.setProperty('--accent-warm', '#e07830');
    document.documentElement.style.setProperty('--destructive', '#dc2626');
  });

  it('returns empty glow for Common rarity', () => {
    const visual = resolveCompanionRarityVisual('Common');
    expect(visual.glowFilter).toBe('');
    expect(visual.ringShadow).toBe('');
  });

  it('derives Epic glow from accent-warm token', () => {
    const visual = resolveCompanionRarityVisual('Epic');
    expect(visual.glowFilter).toContain('drop-shadow');
    expect(visual.textColor).toBe('#e07830');
    expect(visual.ringShadow).toContain('1px');
  });

  it('derives Uncommon glow from primary token', () => {
    const visual = resolveCompanionRarityVisual('Uncommon');
    expect(visual.glowFilter).toContain('drop-shadow');
    expect(visual.textColor).toBe('#588e95');
    expect(visual.ringShadow).toBe('');
  });

  it('derives Rare glow from primary-hover token', () => {
    const visual = resolveCompanionRarityVisual('Rare');
    expect(visual.glowFilter).toContain('drop-shadow');
    expect(visual.textColor).toBe('#4a7d84');
    expect(visual.ringShadow).toBe('');
  });

  it('derives Legendary double glow and ring from accent-warm token', () => {
    const visual = resolveCompanionRarityVisual('Legendary');
    expect(visual.textColor).toBe('#e07830');
    expect(visual.glowFilter.match(/drop-shadow/g)?.length).toBe(2);
    expect(visual.ringShadow).toContain('2px');
  });

  it('maps bubble wait tone to accent-warm', () => {
    const tone = resolveCompanionBubbleTone('wait');
    expect(tone.borderColor).toContain('#e07830');
  });

  it('maps bubble error tone to destructive', () => {
    const tone = resolveCompanionBubbleTone('error');
    expect(tone.borderColor).toContain('#dc2626');
  });
});

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CompanionBones } from '../companionGenerator';

const mockStoreValues: Record<string, unknown> = {
  evolvedRarity: null,
  mascotStatus: null,
  mood: 'neutral',
};

vi.mock('@/store/useCompanionStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) => selector(mockStoreValues),
}));

let mockSelectedAgent: Record<string, unknown> | null = null;

vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) => selector({ selectedAgent: mockSelectedAgent }),
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconGift: () => <span data-testid="icon-gift" />,
}));

import { beforeEach } from 'vitest';
import CompanionSprite from '../CompanionSprite';

const makeBones = (overrides: Partial<CompanionBones> = {}): CompanionBones => ({
  species: '🐱',
  rarity: 'Common',
  stars: 1,
  stats: { debugging: 50, patience: 50, chaos: 50, wisdom: 50, snark: 50 },
  peakStat: 'debugging',
  dumpStat: 'patience',
  shiny: false,
  hat: null,
  defaultName: 'Pip',
  personality: 'analytical but impatient',
  ...overrides,
});

describe('CompanionSprite', () => {
  beforeEach(() => {
    mockSelectedAgent = null;
    mockStoreValues.evolvedRarity = null;
    mockStoreValues.mascotStatus = null;
    mockStoreValues.mood = 'neutral';
  });

  it('renders without crashing', () => {
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    expect(container.querySelector('button')).not.toBeNull();
  });

  it('renders SVG icon for known species', () => {
    const { container } = render(<CompanionSprite bones={makeBones({ species: '🐱' })} animState="idle" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  it('renders emoji fallback for unknown species', () => {
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" speciesOverride="🦄" />);
    expect(container.textContent).toContain('🦄');
  });

  it('renders hat SVG for known hat', () => {
    const { container } = render(<CompanionSprite bones={makeBones({ hat: '👑', rarity: 'Rare' })} animState="idle" />);
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBeGreaterThanOrEqual(2);
  });

  it('renders emoji fallback for unknown hat', () => {
    const bones = makeBones({ hat: '🦄' as never, rarity: 'Rare' });
    const { container } = render(<CompanionSprite bones={bones} animState="idle" />);
    expect(container.textContent).toContain('🦄');
  });

  it('has aria-label for accessibility', () => {
    render(<CompanionSprite bones={makeBones()} animState="idle" />);
    expect(screen.getByLabelText('Companion')).toBeTruthy();
  });

  it('applies animation class based on animState', () => {
    const { container } = render(<CompanionSprite bones={makeBones()} animState="bounce" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('animate-companion-bounce');
  });

  it('shows birthday icon when isBirthday is true', () => {
    render(<CompanionSprite bones={makeBones()} animState="idle" isBirthday />);
    expect(screen.getByTestId('icon-gift')).toBeTruthy();
  });

  it('applies rarity ring classes for Epic', () => {
    const { container } = render(<CompanionSprite bones={makeBones({ rarity: 'Epic' })} animState="idle" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('ring');
  });

  it('respects speciesOverride prop', () => {
    const { container } = render(
      <CompanionSprite bones={makeBones({ species: '🐱' })} animState="idle" speciesOverride="🐶" />,
    );
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  it('respects hatOverride prop', () => {
    const { container } = render(
      <CompanionSprite bones={makeBones({ hat: '👑', rarity: 'Rare' })} animState="idle" hatOverride={null} />,
    );
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBe(1);
  });

  it('maps builtin-developer agent to robot species and fire hat', () => {
    mockSelectedAgent = { id: 'builtin-developer', avatar_url: null };
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBe(2);
  });

  it('maps builtin-researcher agent to owl species and grad hat', () => {
    mockSelectedAgent = { id: 'builtin-researcher', avatar_url: null };
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBe(2);
  });

  it('maps builtin-writer agent to fox species and flower hat', () => {
    mockSelectedAgent = { id: 'builtin-writer', avatar_url: null };
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBe(2);
  });

  it('maps builtin-meeting-scribe agent to panda species', () => {
    mockSelectedAgent = { id: 'builtin-meeting-scribe', avatar_url: null };
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('maps builtin-product-manager agent to octopus species', () => {
    mockSelectedAgent = { id: 'builtin-product-manager', avatar_url: null };
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('uses emoji avatar from agent when available', () => {
    mockSelectedAgent = { id: 'builtin-developer', avatar_url: '🐸' };
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  it('applies working animation class', () => {
    const { container } = render(<CompanionSprite bones={makeBones()} animState="working" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('animate-companion-working');
  });

  it('renders shiny overlay for shiny companion', () => {
    const { container } = render(<CompanionSprite bones={makeBones({ shiny: true })} animState="idle" />);
    expect(container.querySelector('.animate-shimmer-overlay')).not.toBeNull();
  });

  it('applies mood sway animation when mood is happy and no active status', () => {
    mockStoreValues.mood = 'happy';
    mockStoreValues.mascotStatus = 'idle';
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('animate-companion-sway');
  });

  it('applies mood tilt animation for curious mood', () => {
    mockStoreValues.mood = 'curious';
    mockStoreValues.mascotStatus = 'idle';
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('animate-companion-tilt');
  });

  it('does not apply mood animation when mascotStatus is active (thinking)', () => {
    mockStoreValues.mood = 'happy';
    mockStoreValues.mascotStatus = 'thinking';
    const { container } = render(<CompanionSprite bones={makeBones()} animState="working" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).not.toContain('animate-companion-sway');
  });

  it('applies mood idle animation for sleepy mood', () => {
    mockStoreValues.mood = 'sleepy';
    mockStoreValues.mascotStatus = 'sleeping';
    const { container } = render(<CompanionSprite bones={makeBones()} animState="idle" />);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('animate-companion-idle');
  });
});

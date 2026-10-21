import { render, waitFor } from '@testing-library/react';
import * as LucideNamespace from 'lucide-react';
import { Bot } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { findLucideIcon, resolveLucideIcon } from '../lucide-icon-resolver';

const EXPORTED_ICON_NAMES = Object.keys(LucideNamespace).filter(
  (name) => /^[A-Z]/.test(name) && !name.endsWith('Icon') && !name.startsWith('Lucide') && name !== 'Icon',
);

describe('lucide-icon-resolver', () => {
  it('resolves kebab-case and PascalCase names to the same component', () => {
    const kebab = findLucideIcon('check-square');
    expect(kebab).not.toBeNull();
    expect(findLucideIcon('CheckSquare')).toBe(kebab);
  });

  it('returns null for unknown names so callers can pick their own fallback', () => {
    expect(findLucideIcon('definitely-not-an-icon')).toBeNull();
    expect(findLucideIcon('')).toBeNull();
  });

  it('falls back to Bot for unknown names', () => {
    expect(resolveLucideIcon('definitely-not-an-icon')).toBe(Bot);
  });

  it('resolves every icon lucide-react still exports, so no data-driven icon name regresses to the fallback', () => {
    const unresolved = EXPORTED_ICON_NAMES.filter((name) => findLucideIcon(name) === null);
    expect(unresolved).toEqual([]);
  });

  it('shows the Bot placeholder first, then the requested icon with the given size and class', async () => {
    const Sun = resolveLucideIcon('Sun');
    const { container } = render(<Sun size={12} className="probe" />);

    expect(container.querySelector('svg.lucide-bot')).not.toBeNull();

    // The loaded Sun icon has a <circle> body and no longer carries the Bot placeholder class.
    await waitFor(() => expect(container.querySelector('svg circle')).not.toBeNull());
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('class')).not.toContain('lucide-bot');
    expect(svg?.getAttribute('width')).toBe('12');
    expect(svg?.getAttribute('class')).toContain('probe');
  });
});

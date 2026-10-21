import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  HOST_THEME_MUTATION_ATTRIBUTES,
  buildWidgetStyleBlock,
  resolveThemeVars,
  subscribeHostThemeVars,
} from '../widget-theme-bridge';

describe('widget-theme-bridge', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-myrm-theme-profile');
    document.documentElement.removeAttribute('style');
    document.documentElement.classList.remove('dark');
  });

  it('tracks theme profile and style mutations for host sync', () => {
    expect(HOST_THEME_MUTATION_ATTRIBUTES).toContain('data-myrm-theme-profile');
    expect(HOST_THEME_MUTATION_ATTRIBUTES).toContain('style');
    expect(HOST_THEME_MUTATION_ATTRIBUTES).toContain('class');
  });

  it('resolveThemeVars reads inline primary and font override', () => {
    document.documentElement.style.setProperty('--primary', '#2563eb');
    document.documentElement.style.setProperty('--font-override', 'Georgia, serif');

    const vars = resolveThemeVars();

    expect(vars['--primary']).toBe('#2563eb');
    expect(vars['--font-override']).toBe('Georgia, serif');
  });

  it('subscribeHostThemeVars emits when data-myrm-theme-profile changes', async () => {
    document.documentElement.style.setProperty('--primary', '#2563eb');
    const onChange = vi.fn();
    const unsubscribe = subscribeHostThemeVars(onChange);

    expect(onChange).toHaveBeenCalledTimes(1);

    document.documentElement.setAttribute('data-myrm-theme-profile', 'preset-ocean');

    await vi.waitFor(() => {
      expect(onChange.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    expect(onChange.mock.calls.at(-1)?.[0]['--primary']).toBe('#2563eb');

    unsubscribe();
    onChange.mockClear();
    document.documentElement.setAttribute('data-myrm-theme-profile', 'official-default');
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('buildWidgetStyleBlock uses font override when provided', () => {
    const css = buildWidgetStyleBlock({
      '--primary': '#2563eb',
      '--font-override': 'Georgia, serif',
      '--is-dark': '0',
    });

    expect(css).toContain('font-family:Georgia, serif');
  });

  // A widget document is separate from the host page, so the host's reduced-motion block cannot
  // reach it. Without this guard a widget's `button:active` press animation keeps running for a
  // reader who asked the system to stop moving things.
  it('carries a reduced-motion guard so widget animations honour the OS setting', () => {
    const css = buildWidgetStyleBlock({ '--primary': '#2563eb', '--is-dark': '0' });

    expect(css).toContain('@media (prefers-reduced-motion: reduce)');
    expect(css).toContain('animation-duration:0.01ms !important');
    expect(css).toContain('animation-iteration-count:1 !important');
    expect(css).toContain('transition-duration:0.01ms !important');
  });

  // Guards the reason the block must start with the universal selector: widgets the model writes
  // can introduce their own classes, so a rule listing the current animations would miss them.
  it('applies the reduced-motion guard to every element, not to a named list', () => {
    const css = buildWidgetStyleBlock({ '--primary': '#2563eb', '--is-dark': '0' });

    expect(css).toContain('*,*::before,*::after{animation-duration:0.01ms !important');
  });
});

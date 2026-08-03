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
});

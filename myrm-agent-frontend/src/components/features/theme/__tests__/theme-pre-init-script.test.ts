import { describe, expect, it } from 'vitest';
import { THEME_PRE_INIT_SCRIPT } from '../theme-pre-init-script';

describe('THEME_PRE_INIT_SCRIPT', () => {
  it('sets theme-color meta from localStorage theme', () => {
    document.documentElement.innerHTML = '';
    document.head.innerHTML = '<meta name="theme-color" content="#fdfdfb" />';

    localStorage.setItem('theme', 'dark');
    // eslint-disable-next-line no-eval -- inline SSR script parity test
    eval(THEME_PRE_INIT_SCRIPT);

    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('#0a0a0a');
  });

  it('applies skin and font attributes', () => {
    document.documentElement.removeAttribute('data-skin');
    document.documentElement.removeAttribute('data-font');
    document.documentElement.style.removeProperty('--font-override');

    localStorage.setItem('myrm-skin', 'ocean');
    localStorage.setItem('myrm-font', 'system');
    // eslint-disable-next-line no-eval -- inline SSR script parity test
    eval(THEME_PRE_INIT_SCRIPT);

    expect(document.documentElement.getAttribute('data-skin')).toBe('ocean');
    expect(document.documentElement.getAttribute('data-font')).toBe('system');
    expect(document.documentElement.style.getPropertyValue('--font-override')).toContain('ui-sans-serif');
  });
});

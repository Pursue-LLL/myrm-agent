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

  it('applies preinit snapshot tokens when available', () => {
    document.documentElement.removeAttribute('data-myrm-theme-profile');
    localStorage.setItem(
      'myrm-theme-preinit',
      JSON.stringify({
        profileId: 'preset-teal',
        layoutId: 'nav-rail-focus',
        artOn: true,
        isDark: false,
        primary: '#588e95',
        primaryForeground: '#fbfbf8',
        primaryHover: '#4a7d84',
      }),
    );
    // eslint-disable-next-line no-eval -- inline SSR script parity test
    eval(THEME_PRE_INIT_SCRIPT);

    expect(document.documentElement.getAttribute('data-myrm-theme-profile')).toBe('preset-teal');
    expect(document.documentElement.getAttribute('data-myrm-theme-layout')).toBe('nav-rail-focus');
    expect(document.documentElement.getAttribute('data-myrm-theme-art')).toBe('on');
    expect(document.documentElement.style.getPropertyValue('--primary')).toBe('#588e95');
  });

  it('purges legacy skin and font localStorage keys', () => {
    localStorage.setItem('myrm-skin', 'ocean');
    localStorage.setItem('myrm-font', 'system');
    // eslint-disable-next-line no-eval -- inline SSR script parity test
    eval(THEME_PRE_INIT_SCRIPT);

    expect(localStorage.getItem('myrm-skin')).toBeNull();
    expect(localStorage.getItem('myrm-font')).toBeNull();
  });
});

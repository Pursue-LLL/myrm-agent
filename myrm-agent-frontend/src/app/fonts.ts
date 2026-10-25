import localFont from 'next/font/local';

/**
 * Inter is bundled from `src/assets/fonts` (OFL) instead of `next/font/google`:
 * builds and the packaged desktop app must work offline, and the theme engine
 * (`fontId: 'inter'`) only pays off when the glyphs are actually available.
 * CJK intentionally falls through to the platform faces in `--font-sans`.
 */
export const inter = localFont({
  src: '../assets/fonts/InterVariable-latin.woff2',
  weight: '400 600',
  style: 'normal',
  variable: '--font-inter',
  display: 'swap',
  preload: true,
  fallback: [
    'ui-sans-serif',
    'system-ui',
    '-apple-system',
    'BlinkMacSystemFont',
    'Segoe UI',
    'Roboto',
    'Helvetica Neue',
    'PingFang SC',
    'Noto Sans SC',
    'Microsoft YaHei',
    'sans-serif',
  ],
});

/**
 * Accessibility face used by the three `preset-atkinson-*` theme profiles.
 * `preload: false`: it is only fetched when a profile actually selects it, so the
 * default shell keeps its single-font budget while still working offline.
 */
export const atkinson = localFont({
  src: '../assets/fonts/AtkinsonVariable-latin.woff2',
  weight: '400 700',
  style: 'normal',
  variable: '--font-atkinson',
  display: 'swap',
  preload: false,
  fallback: [
    'ui-sans-serif',
    'system-ui',
    '-apple-system',
    'BlinkMacSystemFont',
    'Segoe UI',
    'Roboto',
    'Helvetica Neue',
    'PingFang SC',
    'Noto Sans SC',
    'Microsoft YaHei',
    'sans-serif',
  ],
});

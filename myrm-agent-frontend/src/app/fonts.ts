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

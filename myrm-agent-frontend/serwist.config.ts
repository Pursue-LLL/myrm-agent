import type { BuildOptions } from '@serwist/cli';

const isTauriBuild = process.env.BUILD_MODE === 'tauri';

const config: BuildOptions = {
  swSrc: '.serwist/sw-inject-src.js',
  swDest: 'public/sw.js',
  globDirectory: '.next',
  globPatterns: [
    'static/chunks/**/*.js',
    'static/css/**/*.css',
    'server/app/**/*.html',
  ],
  disablePrecacheManifest: isTauriBuild || process.env.NODE_ENV === 'development',
};

export default config;

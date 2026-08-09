import { existsSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';
import { BUILT_IN_PROVIDERS } from '@/store/config/providerTypes';
import {
  BUILT_IN_PROVIDER_ICON_LOADERS,
  BUILT_IN_PROVIDER_SVG_SLUGS,
} from '../provider-brand-icon-loaders';

const require = createRequire(import.meta.url);

const iconsDir = path.join(path.dirname(require.resolve('@lobehub/icons-static-svg/package.json')), 'icons');

describe('provider brand icon loaders', () => {
  it('covers every built-in provider id with a loader and svg slug', () => {
    for (const providerId of BUILT_IN_PROVIDERS) {
      expect(BUILT_IN_PROVIDER_ICON_LOADERS[providerId]).toBeTypeOf('function');
      expect(BUILT_IN_PROVIDER_SVG_SLUGS[providerId]).toBeTruthy();
    }
    expect(Object.keys(BUILT_IN_PROVIDER_ICON_LOADERS)).toHaveLength(BUILT_IN_PROVIDERS.length);
    expect(Object.keys(BUILT_IN_PROVIDER_SVG_SLUGS)).toHaveLength(BUILT_IN_PROVIDERS.length);
  });

  it('maps each slug to an existing svg file in @lobehub/icons-static-svg', () => {
    for (const slug of Object.values(BUILT_IN_PROVIDER_SVG_SLUGS)) {
      expect(existsSync(path.join(iconsDir, `${slug}.svg`))).toBe(true);
    }
  });

  it('keeps slug SSOT aligned with explicit dynamic import paths', () => {
    for (const [providerId, slug] of Object.entries(BUILT_IN_PROVIDER_SVG_SLUGS)) {
      expect(BUILT_IN_PROVIDER_ICON_LOADERS[providerId as keyof typeof BUILT_IN_PROVIDER_SVG_SLUGS].toString()).toContain(
        `icons/${slug}.svg`,
      );
    }
  });
});

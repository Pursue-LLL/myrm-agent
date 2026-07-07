import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { THEME_PRE_INIT_SCRIPT } from '../theme-pre-init-script';

const publicScript = readFileSync(resolve(process.cwd(), 'public/theme-init.js'), 'utf8');

describe('theme-init public asset parity', () => {
  it('keeps public/theme-init.js aligned with THEME_PRE_INIT_SCRIPT keys', () => {
    for (const key of ['myrm-skin', 'myrm-font', 'theme-color', 'data-skin', 'data-font', '--font-override']) {
      expect(publicScript).toContain(key);
      expect(THEME_PRE_INIT_SCRIPT).toContain(key);
    }
  });

  it('serves font stacks for system and atkinson', () => {
    expect(publicScript).toContain('Atkinson Hyperlegible Next');
    expect(publicScript).toContain('ui-sans-serif');
  });
});

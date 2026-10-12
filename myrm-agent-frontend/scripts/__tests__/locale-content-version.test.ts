import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { computeLocaleContentVersion } from '../locale-content-version';

describe('computeLocaleContentVersion', () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), 'locale-version-'));
    writeFileSync(path.join(dir, 'en.json'), '{"a":"Hello"}');
    writeFileSync(path.join(dir, 'zh.json'), '{"a":"你好"}');
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('is stable for identical content', () => {
    expect(computeLocaleContentVersion(dir)).toBe(computeLocaleContentVersion(dir));
  });

  it('changes when any translation changes', () => {
    const before = computeLocaleContentVersion(dir);
    writeFileSync(path.join(dir, 'zh.json'), '{"a":"你好呀"}');

    expect(computeLocaleContentVersion(dir)).not.toBe(before);
  });

  it('ignores non-locale files such as the generated namespaces directory', () => {
    const before = computeLocaleContentVersion(dir);
    mkdirSync(path.join(dir, 'namespaces'));
    writeFileSync(path.join(dir, 'namespaces', 'common.json'), '{"generated":true}');
    writeFileSync(path.join(dir, 'notes.txt'), 'unrelated');

    expect(computeLocaleContentVersion(dir)).toBe(before);
  });
});

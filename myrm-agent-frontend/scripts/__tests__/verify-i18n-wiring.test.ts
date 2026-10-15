// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// 单测只能证明门禁函数「写对了」，证明不了它「被接上了」：入口漏调一个 verify*，其单测仍然全绿，
// 而生产门禁静默失效。此处断言每个导出的 verify* 至少被入口或兄弟模块实际调用（import 不算）。
const scriptsDir = fileURLToPath(new URL('..', import.meta.url));
const moduleDir = join(scriptsDir, 'verify-i18n');

function readCode(path: string): string {
  return readFileSync(path, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '$1');
}

const sources = [
  join(scriptsDir, 'verify-i18n.mjs'),
  ...readdirSync(moduleDir)
    .filter((file) => file.endsWith('.mjs'))
    .map((file) => join(moduleDir, file)),
].map((path) => ({ path, code: readCode(path) }));

const gates = sources.flatMap(({ path, code }) =>
  [...code.matchAll(/export (?:async )?function (verify\w+)/g)].map((match) => ({ name: match[1], definedIn: path })),
);

describe('verify-i18n gate wiring', () => {
  it('discovers the exported gates', () => {
    expect(gates.length).toBeGreaterThan(0);
  });

  it('calls every exported verify* gate from the entry or a sibling module', () => {
    const unwired = gates
      .filter(({ name, definedIn }) =>
        sources.every(({ path, code }) => path === definedIn || !new RegExp(`\\b${name}\\(`).test(code)),
      )
      .map(({ name }) => name);
    expect(unwired).toEqual([]);
  });
});

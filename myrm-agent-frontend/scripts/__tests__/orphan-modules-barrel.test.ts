// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { ALL, parseFile } from '../orphan-modules-imports';
import { findOrphanModules, type SourceFile } from '../orphan-modules-scan';

const file = (path: string, source = ''): SourceFile => ({ path, source });

const BARREL = 'src/components/kit/index.ts';
const ALPHA = 'src/components/kit/Alpha.tsx';
const BETA = 'src/components/kit/Beta.tsx';

/** 一个 barrel（两条具名再导出）加两个被导出的模块，外加一个读取 `importerSource` 的路由。 */
function scanKit(importerSource: string, barrelSource?: string): readonly string[] {
  return findOrphanModules({
    srcFiles: [
      file('src/app/page.tsx', importerSource),
      file(BARREL, barrelSource ?? "export { Alpha } from './Alpha';\nexport { Beta } from './Beta';"),
      file(ALPHA),
      file(BETA),
    ],
    consumerFiles: [],
  }).orphans;
}

describe('barrel name-level reachability', () => {
  it('keeps only the re-export that an import names alive', () => {
    expect(scanKit("import { Alpha } from '@/components/kit';")).toEqual([BETA]);
  });

  it('keeps every named re-export alive when each one is imported', () => {
    expect(scanKit("import { Alpha, Beta } from '@/components/kit';")).toEqual([]);
  });

  it('keeps the barrel alive but reports every re-export nobody names', () => {
    expect(scanKit("import { somethingElse } from '@/components/kit';")).toEqual([ALPHA, BETA]);
  });

  it('follows an aliased import by its source name, not by the local name', () => {
    expect(scanKit("import { Alpha as Renamed } from '@/components/kit';")).toEqual([BETA]);
  });

  it('follows a re-export alias by its exported name', () => {
    const orphans = scanKit(
      "import { Primary } from '@/components/kit';",
      "export { Alpha as Primary } from './Alpha';\nexport { Beta as Secondary } from './Beta';",
    );
    expect(orphans).toEqual([BETA]);
  });

  it('follows default imports through `export { default } from`', () => {
    const orphans = scanKit(
      "import Alpha from '@/components/kit';",
      "export { default } from './Alpha';\nexport { Beta } from './Beta';",
    );
    expect(orphans).toEqual([BETA]);
  });

  it('keeps a default re-exported under a name alive when that name is imported', () => {
    const orphans = scanKit(
      "import { Alpha } from '@/components/kit';",
      "export { default as Alpha } from './Alpha';\nexport { default as Beta } from './Beta';",
    );
    expect(orphans).toEqual([BETA]);
  });

  it('reads `import type` and inline `type` specifiers like value imports', () => {
    expect(scanKit("import type { Alpha } from '@/components/kit';")).toEqual([BETA]);
    expect(scanKit("import { type Alpha, Beta } from '@/components/kit';")).toEqual([]);
  });

  it('handles multi-line import clauses', () => {
    expect(scanKit("import {\n  Alpha,\n  // Beta,\n} from '@/components/kit';")).toEqual([BETA]);
  });

  it('keeps every re-export alive for forms that read the whole namespace', () => {
    expect(scanKit("import * as kit from '@/components/kit';")).toEqual([]);
    expect(scanKit("import Default, * as kit from '@/components/kit';")).toEqual([]);
    expect(scanKit("import '@/components/kit';")).toEqual([]);
    expect(scanKit("const kit = await import('@/components/kit');")).toEqual([]);
    expect(scanKit("const kit = require('@/components/kit');")).toEqual([]);
  });

  it('treats an import clause it cannot recognise as reading everything', () => {
    expect(scanKit("import {} from '@/components/kit';")).toEqual([]);
  });

  it('forwards the imported name to every `export *` source, because their names are unknown', () => {
    const orphans = scanKit(
      "import { Alpha } from '@/components/kit';",
      "export * from './Alpha';\nexport * from './Beta';",
    );
    expect(orphans).toEqual([]);
  });

  it('keeps a namespace re-export alive when its exported name is imported', () => {
    const orphans = scanKit(
      "import { alpha } from '@/components/kit';",
      "export * as alpha from './Alpha';\nexport * as beta from './Beta';",
    );
    expect(orphans).toEqual([BETA]);
  });

  it('follows nested barrels name by name', () => {
    const orphans = findOrphanModules({
      srcFiles: [
        file('src/app/page.tsx', "import { Alpha } from '@/components';"),
        file('src/components/index.ts', "export { Alpha, Beta } from './kit';"),
        file(BARREL, "export { Alpha } from './Alpha';\nexport { Beta } from './Beta';"),
        file(ALPHA),
        file(BETA),
      ],
      consumerFiles: [],
    }).orphans;
    expect(orphans).toEqual([BETA]);
  });

  it('treats an index file with code as an ordinary module that reads all of its imports', () => {
    const orphans = scanKit(
      "import { helper } from '@/components/kit';",
      "export const helper = 1;\nexport { Alpha } from './Alpha';\nexport { Beta } from './Beta';",
    );
    expect(orphans).toEqual([]);
  });

  it('keeps a barrel that a build config references by path alive in full', () => {
    const result = findOrphanModules({
      srcFiles: [file('src/app/page.tsx'), file(BARREL, "export { Alpha } from './Alpha';"), file(ALPHA)],
      consumerFiles: [file('next.config.ts', "const plugin = './src/components/kit';")],
    });
    expect(result.orphans).toEqual([]);
  });

  it('keeps reaching a re-exported module once any later import names it', () => {
    const orphans = findOrphanModules({
      srcFiles: [
        file('src/app/page.tsx', "import { Alpha } from '@/components/kit';"),
        file('src/app/other/page.tsx', "import { Beta } from '@/components/kit';"),
        file(BARREL, "export { Alpha } from './Alpha';\nexport { Beta } from './Beta';"),
        file(ALPHA),
        file(BETA),
      ],
      consumerFiles: [],
    }).orphans;
    expect(orphans).toEqual([]);
  });
});

describe('parseFile', () => {
  it('classifies an index file made only of re-exports (and a directive) as a barrel', () => {
    const parsed = parseFile(
      BARREL,
      "'use client';\n// public surface\nexport { A, type B } from './A';\nexport * from './b';\nexport * as ns from './c';\nexport type { T } from './t';",
    );
    expect(parsed.barrel?.stars).toEqual(['./b']);
    expect([...(parsed.barrel?.named.keys() ?? [])]).toEqual(['A', 'B', 'ns', 'T']);
    expect(parsed.barrel?.named.get('ns')).toEqual({ specifier: './c', imported: ALL });
  });

  it('does not classify non-index files or index files with other statements as barrels', () => {
    expect(parseFile('src/lib/x.ts', "export { A } from './A';").barrel).toBeNull();
    expect(parseFile(BARREL, "import { A } from './A';\nexport { A };").barrel).toBeNull();
    expect(parseFile(BARREL, "export const x = 1;\nexport { A } from './A';").barrel).toBeNull();
  });

  it('ignores re-exports that only appear in comments', () => {
    const parsed = parseFile(
      BARREL,
      "export { A } from './A';\n// export { B } from './B';\n/* export * from './c'; */",
    );
    expect([...(parsed.barrel?.named.keys() ?? [])]).toEqual(['A']);
    expect(parsed.barrel?.stars).toEqual([]);
  });
});

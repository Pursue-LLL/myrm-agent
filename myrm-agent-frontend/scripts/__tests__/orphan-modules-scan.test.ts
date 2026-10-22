// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { findOrphanModules, isTestSupportFile, type SourceFile } from '../orphan-modules-scan';

const file = (path: string, source = ''): SourceFile => ({ path, source });

const scan = (srcFiles: SourceFile[], consumerFiles: SourceFile[] = []) =>
  findOrphanModules({ srcFiles, consumerFiles });

describe('findOrphanModules', () => {
  it('treats modules reachable from an app route as alive and unreferenced ones as orphans', () => {
    const result = scan([
      file('src/app/page.tsx', "import { Home } from '@/components/Home';"),
      file('src/components/Home.tsx', "import { util } from '../lib/util';"),
      file('src/lib/util.ts'),
      file('src/components/Lonely.tsx'),
    ]);
    expect(result.orphans).toEqual(['src/components/Lonely.tsx']);
    expect(result.scanned).toBe(3);
  });

  it('reaches fixed point: a module only imported by an orphan is an orphan too', () => {
    const result = scan([
      file('src/app/page.tsx'),
      file('src/components/Dead.tsx', "import { helper } from '@/lib/helper';"),
      file('src/lib/helper.ts'),
    ]);
    expect(result.orphans).toEqual(['src/components/Dead.tsx', 'src/lib/helper.ts']);
  });

  it('does not let tests or test-utils keep production code alive', () => {
    const result = scan([
      file('src/app/page.tsx'),
      file('src/lib/tested.ts'),
      file('src/lib/__tests__/tested.test.ts', "import { x } from '../tested';"),
      file('src/lib/viaHelper.ts'),
      file('src/test-utils/helper.ts', "import { y } from '@/lib/viaHelper';"),
      file('src/lib/mockOnly.ts'),
      file('src/__mocks__/mockOnly.mock.ts', "import { z } from '@/lib/mockOnly';"),
    ]);
    expect(result.orphans).toEqual(['src/lib/mockOnly.ts', 'src/lib/tested.ts', 'src/lib/viaHelper.ts']);
  });

  it('does not report tests or test-utils themselves', () => {
    const result = scan([
      file('src/app/page.tsx'),
      file('src/lib/__tests__/a.test.ts'),
      file('src/lib/b.spec.tsx'),
      file('src/test-utils/setup.ts'),
    ]);
    expect(result).toEqual({ scanned: 0, orphans: [] });
  });

  describe('barrels', () => {
    it('does not count an unreferenced barrel as a consumer of the modules it re-exports', () => {
      const result = scan([
        file('src/app/page.tsx'),
        file('src/components/widget/index.ts', "export { Widget } from './Widget';"),
        file('src/components/widget/Widget.tsx'),
      ]);
      expect(result.orphans).toEqual(['src/components/widget/Widget.tsx', 'src/components/widget/index.ts']);
    });

    it('keeps re-exported modules alive when the barrel itself is imported', () => {
      const result = scan([
        file('src/app/page.tsx', "import { Widget } from '@/components/widget';"),
        file('src/components/widget/index.ts', "export * from './Widget';"),
        file('src/components/widget/Widget.tsx'),
      ]);
      expect(result.orphans).toEqual([]);
    });

    it('reports a dead barrel whose children are alive through direct imports', () => {
      const result = scan([
        file('src/app/page.tsx', "import { Widget } from '@/components/widget/Widget';"),
        file('src/components/widget/index.ts', "export { Widget } from './Widget';"),
        file('src/components/widget/Widget.tsx'),
      ]);
      expect(result.orphans).toEqual(['src/components/widget/index.ts']);
    });
  });

  describe('module specifier forms', () => {
    const cases: Array<[string, string]> = [
      ['default import', "import Target from '@/lib/target';"],
      ['named import', "import { a, b } from '@/lib/target';"],
      ['multi-line import', "import {\n  a,\n  b,\n} from '@/lib/target';"],
      ['type import', "import type { T } from '@/lib/target';"],
      ['export-from', "export { a } from '@/lib/target';"],
      ['export star', "export * from '@/lib/target';"],
      ['side-effect import', "import '@/lib/target';"],
      ['dynamic import', "const m = await import('@/lib/target');"],
      ['require', "const { a } = require('@/lib/target');"],
      ['worker url', "new Worker(new URL('../lib/target', import.meta.url));"],
    ];
    it.each(cases)('resolves %s', (_label, source) => {
      const result = scan([file('src/app/page.tsx', source), file('src/lib/target.ts')]);
      expect(result.orphans).toEqual([]);
    });

    it('resolves relative specifiers, directory indexes and .tsx files', () => {
      const result = scan([
        file('src/app/page.tsx', "import { A } from '../components/a'; import { B } from '../components/b';"),
        file('src/components/a.tsx'),
        file('src/components/b/index.ts'),
      ]);
      expect(result.orphans).toEqual([]);
    });

    it('ignores third-party packages and unknown paths', () => {
      const result = scan([file('src/app/page.tsx', "import React from 'react'; import x from './missing';")]);
      expect(result).toEqual({ scanned: 0, orphans: [] });
    });
  });

  describe('comments', () => {
    it('does not treat an import written in a comment as a consumer', () => {
      const result = scan([
        file(
          'src/app/page.tsx',
          "// import { a } from '@/lib/lineComment';\n/* import { b } from '@/lib/blockComment'; */\n/**\n * @example import('@/lib/jsdoc')\n */",
        ),
        file('src/lib/lineComment.ts'),
        file('src/lib/blockComment.ts'),
        file('src/lib/jsdoc.ts'),
      ]);
      expect(result.orphans).toEqual(['src/lib/blockComment.ts', 'src/lib/jsdoc.ts', 'src/lib/lineComment.ts']);
    });

    it('keeps real imports that follow a string containing a double slash', () => {
      const result = scan([
        file('src/app/page.tsx', "const url = 'https://example.com/x';\nimport { a } from '@/lib/target';"),
        file('src/lib/target.ts'),
      ]);
      expect(result.orphans).toEqual([]);
    });
  });

  describe('entries', () => {
    it('treats src/app files, src/middleware.ts and ambient declarations as roots, never as candidates', () => {
      const result = scan([
        file('src/app/api/route.ts', "import { r } from '@/lib/fromRoute';"),
        file('src/middleware.ts', "import { m } from '@/lib/fromMiddleware';"),
        file('src/types/env.d.ts'),
        file('src/lib/litellmRouting.generated.ts'),
        file('src/lib/fromRoute.ts'),
        file('src/lib/fromMiddleware.ts'),
      ]);
      expect(result).toEqual({ scanned: 2, orphans: [] });
    });

    it('does not exempt non-entry files that merely share a Next.js convention name', () => {
      const result = scan([file('src/app/page.tsx'), file('src/lib/error.ts'), file('src/components/layout.ts')]);
      expect(result.orphans).toEqual(['src/components/layout.ts', 'src/lib/error.ts']);
    });
  });

  describe('consumers outside src', () => {
    it('keeps modules alive that a build config references by path string', () => {
      const result = scan(
        [file('src/app/page.tsx'), file('src/i18n/request.ts')],
        [file('next.config.ts', "const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');")],
      );
      expect(result.orphans).toEqual([]);
    });

    it('keeps modules alive that a script imports through a relative path', () => {
      const result = scan(
        [file('src/app/page.tsx'), file('src/store/known.ts')],
        [file('scripts/export.ts', "import { known } from '../src/store/known';")],
      );
      expect(result.orphans).toEqual([]);
    });

    it('resolves alias and bare src/ literals, and follows the consumed module onward', () => {
      const result = scan(
        [
          file('src/app/page.tsx'),
          file('src/lib/a.ts', "import { b } from './b';"),
          file('src/lib/b.ts'),
          file('src/lib/c.ts'),
        ],
        [file('scripts/x.ts', "load('@/lib/a'); load('src/lib/c.ts');")],
      );
      expect(result.orphans).toEqual([]);
    });

    it('does not let unrelated string literals in consumers keep modules alive', () => {
      const result = scan(
        [file('src/app/page.tsx'), file('src/lib/target.ts')],
        [file('scripts/x.ts', "console.log('target', 'lib/target');")],
      );
      expect(result.orphans).toEqual(['src/lib/target.ts']);
    });
  });
});

describe('isTestSupportFile', () => {
  it.each([
    'src/lib/__tests__/a.ts',
    'src/lib/__mocks__/a.ts',
    'src/lib/a.test.ts',
    'src/lib/a.spec.tsx',
    'src/test-utils/setup.ts',
  ])('classifies %s as test support', (path) => {
    expect(isTestSupportFile(path)).toBe(true);
  });

  it.each(['src/lib/a.ts', 'src/lib/tests.ts', 'src/components/test-utils.tsx'])('keeps %s as production', (path) => {
    expect(isTestSupportFile(path)).toBe(false);
  });
});

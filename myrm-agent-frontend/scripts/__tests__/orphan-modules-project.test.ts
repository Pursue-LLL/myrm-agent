// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { CONSUMER_EXTENSIONS, scanProject } from '../orphan-modules-project.mjs';

let root: string;

function write(files: Record<string, string>): void {
  for (const [path, content] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), content);
  }
}

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), 'orphan-project-'));
  write({
    'src/app/page.tsx': "import { Live } from '@/components/Live';\nexport default Live;\n",
    'src/components/Live.tsx': 'export const Live = () => null;\n',
    'src/components/Dead.tsx': 'export const Dead = () => null;\n',
    // 测试 import 被测文件，不能让它“活着”。
    'src/components/__tests__/Dead.test.tsx': "import { Dead } from '../Dead';\nvoid Dead;\n",
    // 项目根的构建配置与 scripts/ 以路径引用的模块是入口。
    'src/lib/viaConfig.ts': 'export const a = 1;\n',
    'src/lib/viaScript.ts': 'export const b = 2;\n',
    'next.config.ts': "export default { plugin: './src/lib/viaConfig.ts' };\n",
    'scripts/tool.mjs': "import '../src/lib/viaScript.ts';\n",
    // 依赖目录里的文件不参与扫描。
    'node_modules/pkg/index.ts': 'export {};\n',
  });
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('scanProject', () => {
  it('reports the module that no entry reaches and keeps those reached by routes, the build config and scripts', () => {
    const { orphans, scanned } = scanProject(root);

    expect(orphans).toEqual(['src/components/Dead.tsx']);
    // 候选模块：Live、Dead、viaConfig、viaScript（`src/app/**` 是入口，不是候选）。
    expect(scanned).toBe(4);
  });

  it('finds no candidate in a tree without src modules, which the gates treat as a broken scan', () => {
    const empty = mkdtempSync(join(tmpdir(), 'orphan-project-empty-'));
    try {
      mkdirSync(join(empty, 'src'));
      mkdirSync(join(empty, 'scripts'));

      expect(scanProject(empty).scanned).toBe(0);
    } finally {
      rmSync(empty, { recursive: true, force: true });
    }
  });
});

describe('CONSUMER_EXTENSIONS', () => {
  it('covers the file kinds that can reference src modules from outside src', () => {
    expect([...CONSUMER_EXTENSIONS].sort()).toEqual(['.cjs', '.js', '.mjs', '.ts']);
  });
});

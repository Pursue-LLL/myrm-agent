/**
 * [INPUT]
 * src/app/globals.css 与 src/app/workspace-code-editor.css 全文。
 * [OUTPUT]
 * Vitest: 工作区代码编辑器的底色合约存在（Monaco 的编辑区与行号槽取应用的 --background，且规则不在 cascade layer 里），且被全局样式引入。
 * [POS]
 * 防退化守卫：Monaco 注入的主题样式不在任何 layer，写进 `@layer` 的覆盖规则永远输给它；这条规则一旦被挪进 layer，
 * 深色主题下编辑器会变回 #1e1e1e，比面板（--background）亮一档，组件测试与 jsdom 都看不出来。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const read = (file: string): string => readFileSync(resolve(process.cwd(), 'src/app', file), 'utf8');

describe('workspace code editor stylesheet', () => {
  const css = read('workspace-code-editor.css');
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, '');

  it('is part of the global stylesheet', () => {
    expect(read('globals.css')).toContain("@import './workspace-code-editor.css';");
  });

  it('paints the editor and its line-number gutter with the page background', () => {
    const block = rules.match(/\.workspace-code-editor\s+\.monaco-editor\s*\{([^}]*)\}/)?.[1] ?? '';
    expect(block).toMatch(/--vscode-editor-background:\s*var\(--background\)/);
    expect(block).toMatch(/--vscode-editorGutter-background:\s*var\(--background\)/);
  });

  it("stays outside any cascade layer, where Monaco's own unlayered theme rules would win", () => {
    expect(rules).not.toContain('@layer');
  });

  it('names no colour of its own', () => {
    expect(rules).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(|oklch\(/i);
  });
});

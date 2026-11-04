/**
 * [INPUT]
 * src/app/globals.css 全文。
 * [OUTPUT]
 * Vitest: `.scroll-fade-x` 只在 `data-fade-start` / `data-fade-end` 标明确有内容被裁的一侧渐隐，放得下时不加遮罩。
 * [POS]
 * 防退化守卫：遮罩若挂在无条件选择器上，放得下的横向滚动区也会被渐隐吃掉两端的控件；各侧宽度变量若不带默认值，
 * 只有一侧被裁时另一侧读到未定义的变量，整条遮罩就失效了。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBALS_CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

const START = String.raw`\.scroll-fade-x\[data-fade-start='true'\]`;
const END = String.raw`\.scroll-fade-x\[data-fade-end='true'\]`;

/** 选择器后紧跟 `{` 的每条规则的声明块；选择器列表里不是最后一项的选择器后面跟的是逗号，不会命中。 */
function declarations(selector: string): string[] {
  return [...GLOBALS_CSS.matchAll(new RegExp(`${selector}\\s*\\{([^}]*)\\}`, 'g'))].map((match) => match[1].trim());
}

describe('.scroll-fade-x edge fade', () => {
  const [eitherSide = ''] = declarations(String.raw`${START},\s*${END}`);

  it('masks an element only once one of its sides is marked as clipped', () => {
    expect(eitherSide).toContain('mask-image: linear-gradient(');
    expect(GLOBALS_CSS).not.toMatch(/\.scroll-fade-x\s*\{[^}]*mask-image/);
  });

  it('defaults both side widths to zero, so a one-sided fade never reads an undefined variable', () => {
    expect(eitherSide).toContain('--scroll-fade-start: 0px;');
    expect(eitherSide).toContain('--scroll-fade-end: 0px;');
    expect(eitherSide).toContain('var(--scroll-fade-start)');
    expect(eitherSide).toContain('calc(100% - var(--scroll-fade-end))');
  });

  it('widens only the side that is clipped', () => {
    expect(declarations(START)).toEqual(['--scroll-fade-start: 1.5rem;']);
    expect(declarations(END)).toContain('--scroll-fade-end: 1.5rem;');
  });
});

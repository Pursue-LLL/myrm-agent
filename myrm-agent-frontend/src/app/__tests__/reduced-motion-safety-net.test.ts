/**
 * [INPUT]
 * src/app/globals.css 全文。
 * [OUTPUT]
 * Vitest: 全局 prefers-reduced-motion 兜底存在，且用的是「瞬时收尾」而不是「直接移除动画」的写法。
 * [POS]
 * 防退化守卫：组件层只有少数几处单独处理了减少动态效果，若全局兜底被删掉或改写成 `animation: none !important`，
 * 全站的持续脉冲/旋转会重新对前庭敏感用户生效，或让依赖 animationend 的浮层提前卸载。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBALS_CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

/** 取出 `@media (prefers-reduced-motion: reduce)` 中命中通用选择器的那一段声明。 */
function universalReducedMotionBlock(css: string): string | undefined {
  const blocks = [...css.matchAll(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\n\}/g)];
  return blocks.map((match) => match[1]).find((body) => /(?:^|\n)\s*\*::after\s*\{/.test(body));
}

describe('global prefers-reduced-motion safety net', () => {
  const block = universalReducedMotionBlock(GLOBALS_CSS);

  it('runs on the universal selector, so no component animation can escape it', () => {
    expect(block).toBeDefined();
    expect(block).toMatch(/(?:^|\n)\s*\*,/);
    expect(block).toContain('*::before');
    expect(block).toContain('*::after');
  });

  it('shortens animation and transition instead of removing them, keeping animationend dispatch alive', () => {
    expect(block).toContain('animation-duration: 0.01ms !important;');
    expect(block).toContain('animation-iteration-count: 1 !important;');
    expect(block).toContain('transition-duration: 0.01ms !important;');
    expect(block).toContain('scroll-behavior: auto !important;');
  });

  it('never disables animation outright on the universal selector', () => {
    expect(block).not.toMatch(/animation:\s*none/);
    expect(block).not.toMatch(/animation-name:\s*none/);
  });
});

/**
 * [INPUT]
 * src/app/globals.css 全文。
 * [OUTPUT]
 * Vitest: 品牌浮起按钮规则不会覆盖 fixed / absolute / sticky 工具类设定的定位与层级。
 * [POS]
 * 防退化守卫：该规则位于 Tailwind 层之外，优先级天然高于 `.fixed`、`.z-50` 等工具类；一旦它无条件写入
 * `position: relative`，悬浮按钮（实时桌面、检查器、快速捕获）会被拉回文档流，并把空聊天页撑高。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBALS_CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

const POSITION_GUARD = ":where(:not([class*='fixed'], [class*='absolute'], [class*='sticky']))";
const BRAND_ELEVATION_TRIGGER = /\.btn-brand-elevation|\.brand-gradient-bg|\.bg-primary\.text-(?:primary-foreground|white)/;

interface CssRule {
  selectors: string[];
  body: string;
}

/** 按顶层逗号切分选择器列表，括号与属性选择器内部的逗号不算分隔符。 */
function splitSelectorList(list: string): string[] {
  const selectors: string[] = [];
  let depth = 0;
  let current = '';
  for (const char of list) {
    if (char === '(' || char === '[') {
      depth += 1;
    } else if (char === ')' || char === ']') {
      depth -= 1;
    }
    if (char === ',' && depth === 0) {
      selectors.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  selectors.push(current.trim());
  return selectors.filter(Boolean);
}

function parseRules(css: string): CssRule[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
  return [...withoutComments.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selectorList, body]) => ({
    selectors: splitSelectorList(selectorList),
    body,
  }));
}

const brandRulesDeclaring = (property: string) =>
  parseRules(GLOBALS_CSS).filter(
    (rule) =>
      rule.selectors.some((selector) => BRAND_ELEVATION_TRIGGER.test(selector)) &&
      new RegExp(`(?:^|[;\\s])${property}\\s*:`).test(rule.body),
  );

describe('brand elevation positioning', () => {
  it.each([['position'], ['z-index']])('guards every selector that declares %s', (property) => {
    const rules = brandRulesDeclaring(property);
    expect(rules.length, `no brand elevation rule declares ${property}`).toBeGreaterThan(0);

    const unguarded = rules.flatMap((rule) => rule.selectors.filter((selector) => !selector.endsWith(POSITION_GUARD)));
    expect(
      unguarded,
      `${property} on these selectors overrides fixed/absolute/sticky utilities; append ${POSITION_GUARD}`,
    ).toEqual([]);
  });

  it('keeps the resting and hover stacking levels apart so the hovered button lifts above its neighbours', () => {
    const levels = brandRulesDeclaring('z-index').map((rule) => rule.body.match(/z-index\s*:\s*(\d+)/)?.[1]);
    expect(levels).toContain('1');
    expect(levels).toContain('2');
  });
});

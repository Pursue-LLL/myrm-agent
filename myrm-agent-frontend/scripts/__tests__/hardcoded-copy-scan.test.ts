// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { findHardcodedCopySites } from '../hardcoded-copy-scan';

const texts = (source: string): string[] => findHardcodedCopySites(source).map((site) => site.text);

describe('findHardcodedCopySites: JSX text', () => {
  it('flags CJK text and reports its 1-based line', () => {
    const source = ['<div>', '  <span>保存</span>', '</div>'].join('\n');
    expect(findHardcodedCopySites(source)).toEqual([{ line: 2, kind: 'text', text: '保存' }]);
  });

  it('flags two adjacent English words but leaves single tokens, numbers and symbols alone', () => {
    expect(texts('<p>Search files</p>')).toEqual(['Search files']);
    expect(texts('<p>ID</p>')).toEqual([]);
    expect(texts('<p>ms</p>')).toEqual([]);
    expect(texts('<p>MCP</p>')).toEqual([]);
    expect(texts('<p>1,024 / 2,048</p>')).toEqual([]);
    expect(texts('<p>·</p>')).toEqual([]);
  });

  it('collapses whitespace and reports the line of the first visible character', () => {
    const source = ['<p>', '', '   No results', '   found', '</p>'].join('\n');
    expect(findHardcodedCopySites(source)).toEqual([{ line: 3, kind: 'text', text: 'No results found' }]);
  });

  it('accepts text that comes from translations', () => {
    expect(texts(`<p>{t('empty')}</p>`)).toEqual([]);
  });
});

describe('findHardcodedCopySites: JSX child expressions', () => {
  it('flags string literals rendered directly, through ternaries, `&&` and `||` / `??`', () => {
    expect(texts(`<p>{'保存设置'}</p>`)).toEqual(['保存设置']);
    expect(findHardcodedCopySites(`<p>{busy ? 'Saving now' : '完成'}</p>`).map((site) => site.text)).toEqual([
      'Saving now',
      '完成',
    ]);
    expect(texts(`<p>{loading && 'Loading data'}</p>`)).toEqual(['Loading data']);
    expect(texts(`<p>{label ?? 'Untitled item'}</p>`)).toEqual(['Untitled item']);
    expect(findHardcodedCopySites(`<p>{'x'}</p>`)).toEqual([]);
  });

  it('flags the static words of a template literal but not one with no words', () => {
    expect(texts('<p>{`已选择 ${count} 项`}</p>')).toEqual(['已选择 项']);
    expect(texts('<p>{`${a}${b}`}</p>')).toEqual([]);
  });

  it('ignores calls, identifiers and strings that are only compared', () => {
    expect(texts(`<p>{t('save')}</p>`)).toEqual([]);
    expect(texts(`<p>{format('Total items')}</p>`)).toEqual([]);
    expect(texts('<p>{title}</p>')).toEqual([]);
    expect(texts(`<p>{mode === 'dark mode' && <i />}</p>`)).toEqual([]);
    expect(texts(`<p>{'Open the panel' && <i />}</p>`)).toEqual([]);
  });
});

describe('findHardcodedCopySites: attributes', () => {
  it('flags copy-bearing attributes written as plain strings or expressions', () => {
    const source = `<>
      <input placeholder="Search files" />
      <button title="删除" aria-label={'Delete this item'} />
      <Field label={ok ? 'Enabled state' : '已禁用'} />
    </>`;
    expect(findHardcodedCopySites(source).map(({ kind, text }) => `${kind}:${text}`)).toEqual([
      'attribute:Search files',
      'attribute:删除',
      'attribute:Delete this item',
      'attribute:Enabled state',
      'attribute:已禁用',
    ]);
  });

  it('covers component-specific placeholder and label props', () => {
    expect(texts(`<Pair keyPlaceholder="Header name" nodeLabel="根节点" />`)).toEqual(['Header name', '根节点']);
  });

  it('ignores attributes that do not carry display copy', () => {
    const source = `<div className="flex items-center" data-testid="main panel" type="button" href="/a b" id="two words" />`;
    expect(texts(source)).toEqual([]);
  });

  it('accepts translated attribute values', () => {
    expect(texts(`<input placeholder={t('search')} aria-label={tCommon('close')} />`)).toEqual([]);
  });
});

describe('findHardcodedCopySites: exemptions', () => {
  it('leaves text inside code-like elements alone, nested elements included', () => {
    expect(texts('<code>npm install foo</code>')).toEqual([]);
    expect(texts('<pre><span>git commit now</span></pre>')).toEqual([]);
    expect(texts('<kbd>Ctrl Enter</kbd>')).toEqual([]);
    expect(texts(`<code>{'npm install foo'}</code>`)).toEqual([]);
    expect(texts('<div>Ctrl Enter</div>')).toEqual(['Ctrl Enter']);
  });

  it('flags a bilingual literal unless the file localizes it at render time', () => {
    const bilingual = `<button title="复制 / Copy" />`;
    expect(texts(bilingual)).toEqual(['复制 / Copy']);

    const localized = `const view = localizeReactNode(<button title="复制 / Copy" />, locale);`;
    expect(texts(localized)).toEqual([]);
  });

  it('still flags plain CJK or English in a file that localizes bilingual literals', () => {
    const source = `
      localizeReactNode(node, locale);
      const view = <><p>仅中文</p><p>Only English</p></>;`;
    expect(texts(source)).toEqual(['仅中文', 'Only English']);
  });
});

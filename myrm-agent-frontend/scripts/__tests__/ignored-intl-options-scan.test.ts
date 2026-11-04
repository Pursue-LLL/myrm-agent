import { describe, expect, it } from 'vitest';

import { findIgnoredIntlOptions } from '../ignored-intl-options-scan.ts';

const scan = (source: string, fileName = 'sample.tsx') => findIgnoredIntlOptions(source, fileName);

describe('findIgnoredIntlOptions', () => {
  it('flags defaultValue and defaultMessage passed to a translator', () => {
    const hits = scan(`
      const a = t('k', { defaultValue: 'x' });
      const b = tChat(\`errorCategories.\${category}\`, { defaultValue: category });
      const c = thinkT(level, { defaultMessage: level });
      const d = tm('k', { defaultMessage: 'x' });
    `);

    expect(hits.map(({ callee, option }) => `${callee}:${option}`)).toEqual([
      't:defaultValue',
      'tChat:defaultValue',
      'thinkT:defaultMessage',
      'tm:defaultMessage',
    ]);
  });

  it('reports the line of the option, also for multi-line calls', () => {
    const hits = scan(`const a = t(
  'k',
  {
    values: 1,
    defaultValue: 'x',
  },
);`);

    expect(hits).toEqual([{ line: 5, callee: 't', option: 'defaultValue' }]);
  });

  it('flags the shorthand and quoted spellings and the rich variant', () => {
    const hits = scan(`
      const a = t('k', { defaultValue });
      const b = t('k', { 'defaultMessage': 'x' });
      const c = t.rich('k', { defaultValue: 'x', b: (chunks) => chunks });
    `);

    expect(hits.map(({ option }) => option)).toEqual(['defaultValue', 'defaultMessage', 'defaultValue']);
  });

  it('flags both options of one call separately', () => {
    expect(scan(`t('k', { defaultMessage: 'x', defaultValue: 'x' });`)).toHaveLength(2);
  });

  it('leaves translator calls without those options alone', () => {
    expect(scan(`const a = t('k', { count: 1 }); const b = t('k');`)).toEqual([]);
  });

  it('leaves non-translator uses of the same names alone', () => {
    const hits = scan(`
      const tabs = <Tabs defaultValue="overview" />;
      readQueueDockCollapsed(chatId, defaultValue);
      params.push({ name: 'x', defaultValue: '' });
      const form = useForm({ defaultValues, defaultValue: 1 });
      toast('saved', { defaultValue: 'x' });
      test('case', { defaultValue: 1 });
      const editor = createEditor({ defaultMessage: 'x' });
    `);

    expect(hits).toEqual([]);
  });

  it('parses plain TypeScript files', () => {
    expect(scan(`export const label = (t: Translate) => t('k', { defaultValue: 'x' });`, 'sample.ts')).toHaveLength(1);
  });
});

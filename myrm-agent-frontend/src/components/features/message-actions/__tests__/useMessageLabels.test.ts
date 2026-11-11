/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';
import { useMessageLabels } from '../useMessageLabels';

const intl = vi.hoisted(() => ({ locale: 'zh' as MockLocale }));
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

describe('useMessageLabels', () => {
  it.each([
    ['zh', { reasoning: '思考过程', sources: '来源', untitledSource: '未命名' }, '目录索引'],
    ['en', { reasoning: 'Reasoning', sources: 'Sources', untitledSource: 'Untitled' }, 'Catalog index'],
  ] as const)('words the labels in the interface language (%s)', (locale, labels, catalogSection) => {
    intl.locale = locale;

    const { sectionLabel, ...words } = renderHook(() => useMessageLabels()).result.current;

    expect(words).toEqual(labels);
    expect(sectionLabel('index_routing')).toBe(catalogSection);
    expect(sectionLabel('Rollback')).toBe('Rollback');
  });

  it('hands back the same object while the language stays, so callers that depend on it do not rerun', () => {
    intl.locale = 'zh';
    const { result, rerender } = renderHook(() => useMessageLabels());
    const first = result.current;

    rerender();

    expect(result.current).toBe(first);
  });
});

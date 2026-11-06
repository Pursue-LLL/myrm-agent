/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import useConfigStore from '@/store/useConfigStore';

import { useNavMoreSections } from '../useNavMoreSections';

describe('useNavMoreSections', () => {
  beforeEach(() => {
    useConfigStore.setState({ enableEvalLab: true });
  });

  it('gives every entry its own icon, so two rows never read as the same thing', () => {
    const { result } = renderHook(() => useNavMoreSections(false));

    const icons = result.current.flatMap((section) => section.items.map((item) => item.icon));
    expect(new Set(icons).size).toBe(icons.length);
  });
});

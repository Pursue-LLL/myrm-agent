import { describe, it, expect } from 'vitest';
import { mergeUiDataModel } from '../mergeUiDataModel';

describe('mergeUiDataModel', () => {
  it('merges top-level scalar keys', () => {
    const result = mergeUiDataModel({ name: '', age: 0 }, { name: 'Alice', age: 30 });
    expect(result).toEqual({ name: 'Alice', age: 30 });
  });

  it('deep-merges nested plain objects without wiping sibling fields', () => {
    const result = mergeUiDataModel(
      { form: { note: '', env: 'staging' } },
      { form: { note: 'confirmed' } },
    );
    expect(result).toEqual({ form: { note: 'confirmed', env: 'staging' } });
  });

  it('replaces arrays by key', () => {
    const result = mergeUiDataModel(
      { items: [{ title: 'A' }] },
      { items: [{ title: 'A' }, { title: 'B' }] },
    );
    expect(result.items).toHaveLength(2);
  });
});

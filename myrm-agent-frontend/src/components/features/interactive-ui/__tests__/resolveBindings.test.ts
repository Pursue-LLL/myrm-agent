import { describe, expect, it } from 'vitest';
import { getValueByPath, resolveBindings } from '../utils';

describe('resolveBindings', () => {
  it('returns the same props reference when no bindings', () => {
    const props = { text: 'static' };
    const result = resolveBindings(props, {}, { status: 'x' });
    expect(result).toBe(props);
  });

  it('resolves bound props from data and keeps unbound static props', () => {
    const props = { text: 'static', variant: 'body' };
    const result = resolveBindings(props, { text: '$.status' }, { status: 'RUNNING' });
    expect(result).toEqual({ text: 'RUNNING', variant: 'body' });
  });

  it('resolves nested JSONPath-style paths', () => {
    const result = resolveBindings(
      { label: 'btn' },
      { label: '$.form.actions.submitLabel' },
      { form: { actions: { submitLabel: 'Deploy' } } },
    );
    expect(result.label).toBe('Deploy');
  });

  it('does not mutate the input props object', () => {
    const props = { text: 'static' };
    resolveBindings(props, { text: '$.status' }, { status: 'NEW' });
    expect(props.text).toBe('static');
  });

  it('overrides props with undefined when data path is missing (data-driven priority)', () => {
    const result = resolveBindings({ text: 'static' }, { text: '$.missing' }, { status: 'x' });
    expect(result).toEqual({ text: undefined });
  });

  it('resolves multiple bound props independently', () => {
    const result = resolveBindings(
      {},
      { text: '$.status', label: '$.action', value: '$.count' },
      { status: 'OK', action: 'Retry', count: 3 },
    );
    expect(result).toEqual({ text: 'OK', label: 'Retry', value: 3 });
  });

  it('supports paths without the $ prefix', () => {
    const result = resolveBindings({ text: '' }, { text: 'status' }, { status: 'READY' });
    expect(result.text).toBe('READY');
  });
});

describe('getValueByPath', () => {
  it('returns undefined for empty path or missing data', () => {
    expect(getValueByPath({ a: 1 }, '')).toBeUndefined();
    expect(getValueByPath({} as Record<string, unknown>, 'a.b')).toBeUndefined();
  });

  it('returns undefined when traversing through non-object values', () => {
    expect(getValueByPath({ a: 1 }, 'a.b')).toBeUndefined();
  });

  it('reads root and nested values', () => {
    expect(getValueByPath({ a: 1 }, 'a')).toBe(1);
    expect(getValueByPath({ a: { b: 2 } }, '$.a.b')).toBe(2);
  });
});

import { describe, expect, it } from 'vitest';
import type { ModelsDevModel } from '@/services/models-dev';
import { pickSubscriptionDefaultModel } from '../subscriptionDefaultModel';

function model(id: string, overrides: Partial<ModelsDevModel> = {}): ModelsDevModel {
  return {
    id,
    name: id,
    tool_call: true,
    release_date: '2026-01-01',
    modalities: { input: ['text'], output: ['text'] },
    ...overrides,
  };
}

/** Same shape as the xAI section of the live models.dev catalog: media models are the newest entries. */
const XAI_CATALOG: ModelsDevModel[] = [
  model('grok-imagine-video-1.5-lite', {
    release_date: '2026-10-01',
    tool_call: false,
    modalities: { input: ['text'], output: ['video'] },
  }),
  model('grok-4.7', { release_date: '2026-09-21' }),
  model('grok-4.6', { release_date: '2026-08-12' }),
  model('grok-imagine-image', {
    release_date: '2026-01-28',
    tool_call: false,
    modalities: { input: ['text'], output: ['image', 'pdf'] },
  }),
  model('grok-4.20-multi-agent-0309', { release_date: '2026-03-09', tool_call: false }),
];

describe('pickSubscriptionDefaultModel', () => {
  it('picks the newest chat model even when media models were released later', () => {
    expect(pickSubscriptionDefaultModel(XAI_CATALOG)).toBe('grok-4.7');
  });

  it('does not depend on the catalog order', () => {
    expect(pickSubscriptionDefaultModel([...XAI_CATALOG].reverse())).toBe('grok-4.7');
  });

  it('skips deprecated models', () => {
    const catalog = [model('new', { release_date: '2026-06-01', status: 'deprecated' }), model('old')];
    expect(pickSubscriptionDefaultModel(catalog)).toBe('old');
  });

  it('skips models without explicit tool calling', () => {
    const catalog = [
      model('no-tools', { release_date: '2026-06-01', tool_call: false }),
      model('unknown-tools', { release_date: '2026-05-01', tool_call: undefined }),
      model('agent-capable'),
    ];
    expect(pickSubscriptionDefaultModel(catalog)).toBe('agent-capable');
  });

  it('skips models that do not output text', () => {
    const catalog = [
      model('image-only', { release_date: '2026-06-01', modalities: { input: ['text'], output: ['image'] } }),
      model('text-model'),
    ];
    expect(pickSubscriptionDefaultModel(catalog)).toBe('text-model');
  });

  it.each([
    ['legacy array modalities', ['text', 'image']],
    ['missing modalities', undefined],
    ['missing output list', { input: ['text'] }],
  ])('accepts a model whose output modality is unspecified (%s)', (_label, modalities) => {
    expect(pickSubscriptionDefaultModel([model('unspecified', { modalities })])).toBe('unspecified');
  });

  it('ranks entries without a release date last', () => {
    const catalog = [model('undated', { release_date: undefined }), model('dated', { release_date: '2024-01-01' })];
    expect(pickSubscriptionDefaultModel(catalog)).toBe('dated');
  });

  it('orders partial dates chronologically', () => {
    const catalog = [model('march', { release_date: '2026-03' }), model('april', { release_date: '2026-04' })];
    expect(pickSubscriptionDefaultModel(catalog)).toBe('april');
  });

  it('breaks release-date ties by id so the pick is deterministic', () => {
    const tied = [model('b-model'), model('a-model')];
    expect(pickSubscriptionDefaultModel(tied)).toBe('a-model');
    expect(pickSubscriptionDefaultModel([...tied].reverse())).toBe('a-model');
  });

  it('does not mutate the catalog it is given', () => {
    const catalog = Object.freeze([...XAI_CATALOG]);
    expect(() => pickSubscriptionDefaultModel(catalog)).not.toThrow();
    expect(catalog.map((entry) => entry.id)).toEqual(XAI_CATALOG.map((entry) => entry.id));
  });

  it.each([[[]], [[model('video-only', { tool_call: false })]]])('returns null when nothing qualifies', (catalog) => {
    expect(pickSubscriptionDefaultModel(catalog)).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';
import {
  buildLearnSlashMessageFromInput,
  composeLearnSlashMessage,
  parseLearnSlashInput,
} from '../composeLearnSlashMessage';

describe('composeLearnSlashMessage', () => {
  it('returns null when all fields are empty', () => {
    expect(composeLearnSlashMessage({})).toBeNull();
    expect(composeLearnSlashMessage({ directory: '  ', url: '', text: '\n' })).toBeNull();
  });

  it('composes Hermes-style segments into raw /learn', () => {
    expect(
      composeLearnSlashMessage({
        directory: '~/projects/acme-sdk',
        url: 'https://docs.example.com/api',
        text: 'focus on auth + pagination',
      }),
    ).toBe(
      '/learn local source: ~/projects/acme-sdk; URL: https://docs.example.com/api; focus on auth + pagination',
    );
  });

  it('flattens multiline text', () => {
    expect(
      composeLearnSlashMessage({
        text: 'line one\n\nline two',
      }),
    ).toBe('/learn line one line two');
  });
});

describe('parseLearnSlashInput', () => {
  it('strips /learn prefix case-insensitively', () => {
    expect(parseLearnSlashInput('/learn https://docs.example.com')).toBe('https://docs.example.com');
    expect(parseLearnSlashInput('/LEARN foo bar')).toBe('foo bar');
  });
});

describe('buildLearnSlashMessageFromInput', () => {
  it('preserves bare /learn for server default args', () => {
    expect(buildLearnSlashMessageFromInput('/learn')).toBe('/learn');
  });

  it('normalizes full slash input', () => {
    expect(buildLearnSlashMessageFromInput('/learn URL: https://example.com')).toBe(
      '/learn URL: https://example.com',
    );
  });
});

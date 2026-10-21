import { describe, it, expect } from 'vitest';
import {
  BRAND_KEY_PREFIX,
  brandProfileKey,
  brandFieldFromProfileKey,
  extractBrandValues,
  validateBrandField,
  isBrandProfileKey,
  toBrandEntries,
  isColorField,
  isLongTextField,
  type BrandFieldKey,
} from '../brandSchema';

describe('brandSchema', () => {
  describe('brandProfileKey / brandFieldFromProfileKey', () => {
    it('prepends the brand prefix', () => {
      expect(brandProfileKey('primary_color')).toBe(`${BRAND_KEY_PREFIX}primary_color`);
      expect(brandProfileKey('name')).toBe(`${BRAND_KEY_PREFIX}name`);
    });

    it('round-trips known fields', () => {
      const keys: BrandFieldKey[] = [
        'name',
        'tagline',
        'primary_color',
        'secondary_color',
        'accent_color',
        'font',
        'tone',
        'taboos',
      ];
      for (const key of keys) {
        expect(brandFieldFromProfileKey(brandProfileKey(key))).toBe(key);
      }
    });

    it('returns null for non-brand keys', () => {
      expect(brandFieldFromProfileKey('other_key')).toBeNull();
      expect(brandFieldFromProfileKey('')).toBeNull();
    });

    it('returns null for unknown brand-prefixed fields', () => {
      expect(brandFieldFromProfileKey(`${BRAND_KEY_PREFIX}unknown`)).toBeNull();
    });
  });

  describe('isBrandProfileKey', () => {
    it('matches brand-prefixed keys', () => {
      expect(isBrandProfileKey('brand_name')).toBe(true);
      expect(isBrandProfileKey('brand_primary_color')).toBe(true);
    });

    it('rejects non-brand or empty keys', () => {
      expect(isBrandProfileKey('name')).toBe(false);
      expect(isBrandProfileKey('')).toBe(false);
      expect(isBrandProfileKey(undefined)).toBe(false);
      expect(isBrandProfileKey(null)).toBe(false);
    });
  });

  describe('extractBrandValues', () => {
    it('extracts only known brand fields with non-empty values', () => {
      const values = extractBrandValues([
        { key: 'brand_name', value: 'Aurora' },
        { key: 'brand_primary_color', value: '#6C5CE7' },
        { key: 'brand_unknown', value: 'x' },
        { key: 'other', value: 'y' },
        { key: 'brand_tone', value: '  ' },
      ]);
      expect(values).toEqual({
        name: 'Aurora',
        primary_color: '#6C5CE7',
      });
    });

    it('handles null values and empty inputs', () => {
      expect(extractBrandValues([])).toEqual({});
      expect(extractBrandValues([{ key: 'brand_name', value: null }])).toEqual({});
    });
  });

  describe('validateBrandField', () => {
    it('rejects empty values as required', () => {
      expect(validateBrandField('name', '')).toBe('required');
      expect(validateBrandField('primary_color', '   ')).toBe('required');
    });

    it('accepts valid hex colors', () => {
      expect(validateBrandField('primary_color', '#6C5CE7')).toBeNull();
      expect(validateBrandField('accent_color', '#abc')).toBeNull();
    });

    it('rejects invalid hex colors', () => {
      expect(validateBrandField('primary_color', 'red')).toBe('invalidHex');
      expect(validateBrandField('secondary_color', '#12')).toBe('invalidHex');
      expect(validateBrandField('accent_color', '123456')).toBe('invalidHex');
    });

    it('accepts any non-empty text for text fields', () => {
      expect(validateBrandField('name', 'Aurora')).toBeNull();
      expect(validateBrandField('tone', 'Professional, warm')).toBeNull();
      expect(validateBrandField('taboos', 'No humor')).toBeNull();
    });
  });

  describe('toBrandEntries', () => {
    it('builds ordered entries from known brand memories', () => {
      const entries = toBrandEntries([
        { key: 'brand_accent_color', value: '#10B981' },
        { key: 'brand_name', value: 'Aurora' },
      ]);
      expect(entries.map((e) => e.field)).toEqual(['name', 'accent_color']);
      expect(entries[0]).toEqual({ field: 'name', key: 'brand_name', value: 'Aurora' });
      expect(entries[1]).toEqual({
        field: 'accent_color',
        key: 'brand_accent_color',
        value: '#10B981',
      });
    });

    it('returns empty array when no brand memories', () => {
      expect(toBrandEntries([{ key: 'other', value: 'x' }])).toEqual([]);
    });
  });

  describe('field classifiers', () => {
    it('classifies color and long-text fields', () => {
      expect(isColorField('primary_color')).toBe(true);
      expect(isColorField('secondary_color')).toBe(true);
      expect(isColorField('accent_color')).toBe(true);
      expect(isColorField('name')).toBe(false);
      expect(isLongTextField('tagline')).toBe(true);
      expect(isLongTextField('taboos')).toBe(true);
      expect(isLongTextField('font')).toBe(false);
    });
  });
});

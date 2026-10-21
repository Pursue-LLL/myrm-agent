import { describe, it, expect } from 'vitest';
import {
  matchesSchemaGroup,
  matchesSchemaSection,
  matchesSchemaVisibility,
  resolveEnumLabel,
  resolveFieldLabels,
  supportsSchemaControl,
} from '@/lib/config/schemaFormUtils';

describe('schemaFormUtils', () => {
  describe('matchesSchemaSection', () => {
    it('returns true for all fields when section is omitted', () => {
      expect(matchesSchemaSection({ 'x-ui-section': 'memory' }, undefined)).toBe(true);
    });

    it('matches backend x-ui-section metadata', () => {
      expect(matchesSchemaSection({ 'x-ui-section': 'preferences' }, 'preferences')).toBe(true);
      expect(matchesSchemaSection({ 'x-ui-section': 'memory' }, 'preferences')).toBe(false);
    });
  });

  describe('matchesSchemaGroup', () => {
    it('defaults to basic when x-ui-group is missing', () => {
      expect(matchesSchemaGroup({}, 'basic')).toBe(true);
      expect(matchesSchemaGroup({}, 'advanced')).toBe(false);
    });

    it('matches backend x-ui-group metadata', () => {
      expect(matchesSchemaGroup({ 'x-ui-group': 'advanced' }, 'advanced')).toBe(true);
      expect(matchesSchemaGroup({ 'x-ui-group': 'advanced' }, 'basic')).toBe(false);
    });
  });

  describe('matchesSchemaVisibility', () => {
    it('hides local-only fields outside local mode', () => {
      expect(matchesSchemaVisibility({ 'x-ui-visible-if': 'local' }, { isLocal: false, value: {} })).toBe(false);
      expect(matchesSchemaVisibility({ 'x-ui-visible-if': 'local' }, { isLocal: true, value: {} })).toBe(true);
    });

    it('requires dependent field value when x-ui-requires-field is set', () => {
      const prop = { 'x-ui-visible-if': 'local', 'x-ui-requires-field': 'enableCostEstimation' };
      expect(
        matchesSchemaVisibility(prop, {
          isLocal: true,
          value: { enableCostEstimation: false },
        }),
      ).toBe(false);
      expect(
        matchesSchemaVisibility(prop, {
          isLocal: true,
          value: { enableCostEstimation: true },
        }),
      ).toBe(true);
    });
  });

  describe('supportsSchemaControl', () => {
    it('supports boolean, string, and enum fields', () => {
      expect(supportsSchemaControl('boolean', false)).toBe(true);
      expect(supportsSchemaControl('string', false)).toBe(true);
      expect(supportsSchemaControl('string', true)).toBe(true);
      expect(supportsSchemaControl('array', false)).toBe(false);
    });
  });

  describe('resolveFieldLabels', () => {
    const translate = (key: string) =>
      ({
        fetchRawWebpage: 'Fetch Raw Webpage',
        fetchRawWebpageDesc: 'Keep raw HTML content',
        extractDocumentText: 'Extract Attachment Text',
        extractDocumentTextDesc: 'Convert PDF/Office attachments to text before sending to the model',
        enableWebNotifications: 'Web Notifications',
        webNotifications: 'Web Notifications Legacy',
        webNotificationsDesc: 'Browser notifications',
      })[key] ?? `settings.${key}`;

    const hasKey = (key: string) =>
      [
        'fetchRawWebpage',
        'fetchRawWebpageDesc',
        'extractDocumentText',
        'extractDocumentTextDesc',
        'enableWebNotifications',
        'webNotifications',
        'webNotificationsDesc',
      ].includes(key);

    it('uses locale keys before schema description', () => {
      const labels = resolveFieldLabels(
        translate,
        hasKey,
        'settings',
        'fetchRawWebpage',
        { description: '获取原始网页' },
        'en',
      );
      expect(labels.title).toBe('Fetch Raw Webpage');
      expect(labels.desc).toBe('Keep raw HTML content');
    });

    it('uses alias keys for legacy field names', () => {
      const labels = resolveFieldLabels(
        translate,
        hasKey,
        'settings',
        'enableWebNotifications',
        { description: '启用 Web 通知' },
        'en',
      );
      expect(labels.title).toBe('Web Notifications');
      expect(labels.desc).toBe('Browser notifications');
    });

    it('falls back to field key for non-Chinese locales without translations', () => {
      const labels = resolveFieldLabels(
        () => 'settings.unknownField',
        () => false,
        'settings',
        'unknownField',
        { description: '中文描述' },
        'en',
      );
      expect(labels.title).toBe('unknownField');
      expect(labels.desc).toBe('');
    });

    it('falls back to schema description for Chinese locales', () => {
      const labels = resolveFieldLabels(
        () => 'settings.unknownField',
        () => false,
        'settings',
        'unknownField',
        { description: '中文描述' },
        'zh',
      );
      expect(labels.title).toBe('中文描述');
    });
  });

  describe('resolveEnumLabel', () => {
    const translate = (key: string) =>
      ({
        'webTts.browser': 'Browser Built-in',
        'webTts.openai': 'OpenAI TTS',
      })[key] ?? key;

    const hasKey = (key: string) => key.startsWith('webTts.');

    it('maps webTtsProvider enum values to webTts locale keys', () => {
      expect(resolveEnumLabel(translate, hasKey, 'settings', 'webTtsProvider', 'browser')).toBe('Browser Built-in');
      expect(resolveEnumLabel(translate, hasKey, 'settings', 'webTtsProvider', 'openai')).toBe('OpenAI TTS');
    });
  });
});

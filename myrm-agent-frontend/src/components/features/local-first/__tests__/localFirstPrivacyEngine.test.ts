import { describe, expect, it } from 'vitest';
import {
  buildRoamingRecord,
  calculateSimpleChecksum,
  convertJsonToFormat,
  sanitizeClientSideData,
} from '../localFirstPrivacyEngine';

describe('localFirstPrivacyEngine', () => {
  describe('sanitizeClientSideData', () => {
    it('masks phone numbers accurately', () => {
      const input = '我的联系方式是 13812345678 请注意查收。';
      const result = sanitizeClientSideData(input);

      expect(result.sanitizedText).toBe('我的联系方式是 138****5678 请注意查收。');
      expect(result.maskedCount).toBe(1);
      expect(result.detectedTypes).toContain('手机号');
    });

    it('masks email addresses accurately', () => {
      const input = '联系邮箱 alice.smith@example.com';
      const result = sanitizeClientSideData(input);

      expect(result.sanitizedText).toBe('联系邮箱 a***@example.com');
      expect(result.maskedCount).toBe(1);
      expect(result.detectedTypes).toContain('电子邮箱');
    });

    it('masks OpenAI api keys accurately', () => {
      const input = '配置 sk-abcdef1234567890qwerty 到环境变量';
      const result = sanitizeClientSideData(input);

      expect(result.sanitizedText).toContain('sk-abcd****erty');
      expect(result.maskedCount).toBe(1);
      expect(result.detectedTypes).toContain('API Key');
    });

    it('masks 18-digit identity card numbers accurately', () => {
      const input = '身份证号 11010119900307234X 已经核验完毕';
      const result = sanitizeClientSideData(input);

      expect(result.sanitizedText).toBe(
        '身份证号 110101********234X 已经核验完毕',
      );
      expect(result.maskedCount).toBe(1);
      expect(result.detectedTypes).toContain('身份证号');
    });

    it('handles multiple mixed sensitive types in one text', () => {
      const input =
        '用户 13900001111 身份证 11010119900307234X 邮箱 test@domain.org 密钥 sk-12345678901234567890';
      const result = sanitizeClientSideData(input);

      expect(result.maskedCount).toBe(4);
      expect(result.detectedTypes).toHaveLength(4);
      expect(result.executionTimeMs).toBeGreaterThanOrEqual(0);
    });
  });

  describe('convertJsonToFormat', () => {
    const sampleJsonArray = JSON.stringify([
      { name: 'Alice', role: 'Dev', age: 30 },
      { name: 'Bob', role: 'Designer', age: 28 },
    ]);

    it('converts json array to csv', () => {
      const csv = convertJsonToFormat(sampleJsonArray, 'csv');
      expect(csv).toContain('name,role,age');
      expect(csv).toContain('Alice,Dev,30');
      expect(csv).toContain('Bob,Designer,28');
    });

    it('converts json array to markdown table', () => {
      const md = convertJsonToFormat(sampleJsonArray, 'markdown_table');
      expect(md).toContain('| name | role | age |');
      expect(md).toContain('| --- | --- | --- |');
      expect(md).toContain('| Alice | Dev | 30 |');
    });

    it('converts json to yaml representation', () => {
      const yaml = convertJsonToFormat(sampleJsonArray, 'yaml');
      expect(yaml).toContain('- name: Alice');
      expect(yaml).toContain('  role: Dev');
    });

    it('throws error for invalid json syntax', () => {
      expect(() => convertJsonToFormat('{ bad json }', 'csv')).toThrowError(
        '无效的 JSON 格式',
      );
    });
  });

  describe('calculateSimpleChecksum & buildRoamingRecord', () => {
    it('generates consistent checksum for same content', () => {
      const hash1 = calculateSimpleChecksum('{"a":1}');
      const hash2 = calculateSimpleChecksum('{"a":1}');
      const hash3 = calculateSimpleChecksum('{"a":2}');

      expect(hash1).toBe(hash2);
      expect(hash1).not.toBe(hash3);
    });

    it('builds roaming record with checksum and version', () => {
      const record = buildRoamingRecord('user-pref', { theme: 'dark' }, 'upstash_redis', 2);
      expect(record.key).toBe('user-pref');
      expect(record.backend).toBe('upstash_redis');
      expect(record.version).toBe(2);
      expect(record.checksum).toContain('chk-');
      expect(record.updatedAt).toBeGreaterThan(0);
    });
  });
});

import { describe, it, expect } from 'vitest';
import { safeBase64DecodeUtf8, safeBase64EncodeUtf8 } from '../encodingUtils';

describe('encodingUtils', () => {
  it('should correctly encode and decode pure ASCII text', () => {
    const text = 'Hello world! 12345';
    const encoded = safeBase64EncodeUtf8(text);
    const decoded = safeBase64DecodeUtf8(encoded);
    expect(decoded).toBe(text);
  });

  it('should correctly encode and decode Chinese text without Latin1 corruption', () => {
    const text = '<h1>欢迎来到知识库，AI 交互卡片</h1><p>状态：已完成</p>';
    const encoded = safeBase64EncodeUtf8(text);
    const decoded = safeBase64DecodeUtf8(encoded);
    expect(decoded).toBe(text);
  });

  it('should correctly decode UTF-8 Base64 containing complex Emoji and symbols', () => {
    const text = '🚀 知识库看板 📊 | 状态: ✅ 100% | 评分: ⭐⭐⭐⭐⭐';
    const encoded = safeBase64EncodeUtf8(text);
    const decoded = safeBase64DecodeUtf8(encoded);
    expect(decoded).toBe(text);
  });

  it('should handle empty or invalid inputs gracefully', () => {
    expect(safeBase64DecodeUtf8('')).toBe('');
    expect(safeBase64DecodeUtf8('   ')).toBe('');
    expect(safeBase64EncodeUtf8('')).toBe('');
  });
});

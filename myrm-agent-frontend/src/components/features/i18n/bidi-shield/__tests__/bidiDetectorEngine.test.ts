import { describe, it, expect } from 'vitest';
import {
  isRtlChar,
  isLtrChar,
  detectTextDirection,
  splitBidiSegments,
  WINDOWS_RTL_SAFE_FONT_STACK,
} from '../bidiDetectorEngine';

describe('bidiDetectorEngine', () => {
  describe('isRtlChar & isLtrChar', () => {
    it('正确识别阿拉伯与希伯来字符为 RTL', () => {
      expect(isRtlChar('ي')).toBe(true);
      expect(isRtlChar('م')).toBe(true);
      expect(isRtlChar('ש')).toBe(true);
      expect(isRtlChar('A')).toBe(false);
      expect(isRtlChar('中')).toBe(false);
    });

    it('正确识别英文与中文为 LTR', () => {
      expect(isLtrChar('A')).toBe(true);
      expect(isLtrChar('z')).toBe(true);
      expect(isLtrChar('文')).toBe(true);
      expect(isLtrChar('ي')).toBe(false);
    });
  });

  describe('detectTextDirection', () => {
    it('对空文本或仅空白返回默认 ltr 方向', () => {
      const result = detectTextDirection('   ');
      expect(result.dominantDirection).toBe('ltr');
      expect(result.rtlRatio).toBe(0);
      expect(result.containsRtl).toBe(false);
      expect(result.segments).toEqual([]);
    });

    it('纯中文与纯英文文本被判定为 ltr', () => {
      const zhResult = detectTextDirection('这是一个纯中文排版测试。');
      expect(zhResult.dominantDirection).toBe('ltr');
      expect(zhResult.containsRtl).toBe(false);

      const enResult = detectTextDirection('Hello, this is a plain English text.');
      expect(enResult.dominantDirection).toBe('ltr');
      expect(enResult.containsRtl).toBe(false);
    });

    it('阿拉伯语文本被精准识别为 rtl 且 containsRtl 为 true', () => {
      const arResult = detectTextDirection('مرحبا بكم في واجهة الوكيل الذكي');
      expect(arResult.dominantDirection).toBe('rtl');
      expect(arResult.containsRtl).toBe(true);
      expect(arResult.rtlRatio).toBeGreaterThan(0.8);
    });
  });

  describe('splitBidiSegments', () => {
    it('空字符串返回空数组', () => {
      expect(splitBidiSegments('')).toEqual([]);
    });

    it('将嵌入的反引号代码块与变量名安全切片为 LTR 隔离块', () => {
      const mixedText = 'يرجى مراجعة `auth_token` والتأكد من القيمة.';
      const segments = splitBidiSegments(mixedText);

      expect(segments.length).toBeGreaterThanOrEqual(3);

      const codeSegment = segments.find((s) => s.text === '`auth_token`');
      expect(codeSegment).toBeDefined();
      expect(codeSegment?.isCodeOrVariable).toBe(true);
      expect(codeSegment?.isRtl).toBe(false);
    });

    it('将混合的 URL 链接切分为独立 LTR 隔离段', () => {
      const urlText = 'الرابط הוא https://myrm.internal/api للمزيد من المعلومات.';
      const segments = splitBidiSegments(urlText);

      const urlSegment = segments.find((s) => s.text.includes('https://myrm.internal/api'));
      expect(urlSegment).toBeDefined();
      expect(urlSegment?.isCodeOrVariable).toBe(true);
      expect(urlSegment?.isRtl).toBe(false);
    });
  });

  describe('WINDOWS_RTL_SAFE_FONT_STACK', () => {
    it('包含 Segoe UI 与 Noto Sans Arabic 稳健回退字体', () => {
      expect(WINDOWS_RTL_SAFE_FONT_STACK).toContain('Segoe UI');
      expect(WINDOWS_RTL_SAFE_FONT_STACK).toContain('Noto Sans Arabic');
      expect(WINDOWS_RTL_SAFE_FONT_STACK).toContain('Tahoma');
    });
  });
});

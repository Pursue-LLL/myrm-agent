import { describe, it, expect, vi } from 'vitest';
import {
  calculateEditorMetrics,
  BUILTIN_EDITOR_TEMPLATES,
  isTauriEnvironment,
  dispatchExternalEditorEvent,
} from '../modalEditorEngine';

describe('modalEditorEngine', () => {
  describe('calculateEditorMetrics', () => {
    it('returns zeroes for empty or whitespace-only text', () => {
      expect(calculateEditorMetrics('')).toEqual({
        charCount: 0,
        wordCount: 0,
        lineCount: 0,
      });
      expect(calculateEditorMetrics('   \n  ')).toEqual({
        charCount: 0,
        wordCount: 0,
        lineCount: 0,
      });
    });

    it('calculates metrics for English text accurately', () => {
      const text = 'Hello world\nThis is a test';
      const metrics = calculateEditorMetrics(text);
      expect(metrics.charCount).toBe(text.length);
      expect(metrics.wordCount).toBe(6); // Hello, world, This, is, a, test
      expect(metrics.lineCount).toBe(2);
    });

    it('calculates metrics for mixed Chinese and English text', () => {
      const text = '产品需求规范 PRD\n第一阶段交付完成 100%';
      const metrics = calculateEditorMetrics(text);
      expect(metrics.charCount).toBe(text.length);
      // 中文字符: 产, 品, 需, 求, 规, 范, 第, 一, 阶, 段, 交, 付, 完, 成 (14)
      // 英文/数字: PRD, 100 (2)
      // 总词数 = 16
      expect(metrics.wordCount).toBe(16);
      expect(metrics.lineCount).toBe(2);
    });
  });

  describe('BUILTIN_EDITOR_TEMPLATES', () => {
    it('contains all 4 standard templates with non-empty content', () => {
      expect(BUILTIN_EDITOR_TEMPLATES.length).toBe(4);
      const ids = BUILTIN_EDITOR_TEMPLATES.map((t) => t.id);
      expect(ids).toContain('prd-spec');
      expect(ids).toContain('bug-diagnosis');
      expect(ids).toContain('code-refactor');
      expect(ids).toContain('doc-review');

      for (const tmpl of BUILTIN_EDITOR_TEMPLATES) {
        expect(tmpl.name.trim().length).toBeGreaterThan(0);
        expect(tmpl.description.trim().length).toBeGreaterThan(0);
        expect(tmpl.content.trim().length).toBeGreaterThan(20);
      }
    });
  });

  describe('isTauriEnvironment', () => {
    it('detects standard web environment as false', () => {
      expect(isTauriEnvironment()).toBe(false);
    });

    it('detects Tauri environment when window flags exist', () => {
      Object.assign(window, { __TAURI__: {} });
      expect(isTauriEnvironment()).toBe(true);
      delete (window as Record<string, unknown>).__TAURI__;
    });
  });

  describe('dispatchExternalEditorEvent', () => {
    it('dispatches custom myrm:open-external-editor event on window', () => {
      const listener = vi.fn();
      window.addEventListener('myrm:open-external-editor', listener);

      const payload = {
        sessionId: 'test-session-123',
        content: '# Test Document',
      };

      const result = dispatchExternalEditorEvent(payload);
      expect(result).toBe(true);
      expect(listener).toHaveBeenCalledTimes(1);

      const event = listener.mock.calls[0][0] as CustomEvent;
      expect(event.detail).toEqual(payload);

      window.removeEventListener('myrm:open-external-editor', listener);
    });
  });
});

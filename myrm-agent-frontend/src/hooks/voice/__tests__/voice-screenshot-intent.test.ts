import { describe, expect, it } from 'vitest';
import {
  cleanSpokenTranscript,
  detectVoiceVisualIntent,
} from '@/hooks/voice/voice-screenshot-intent';

describe('voice-screenshot-intent', () => {
  describe('cleanSpokenTranscript', () => {
    it('strips colloquial leading filler phrases', () => {
      expect(cleanSpokenTranscript('请帮我看下这个报错')).toBe('这个报错');
      expect(cleanSpokenTranscript('麻烦你给我查一下这段代码')).toBe('这段代码');
      expect(cleanSpokenTranscript('现在看一下屏幕上有什么')).toBe('屏幕上有什么');
    });
  });

  describe('detectVoiceVisualIntent', () => {
    it('detects error diagnosis visual intent', () => {
      const res = detectVoiceVisualIntent('请帮我看下这个报错怎么解决');
      expect(res.hasVisualIntent).toBe(true);
      expect(res.category).toBe('error_diagnosis');
      expect(res.confidence).toBeGreaterThanOrEqual(0.9);
      expect(res.triggers.length).toBeGreaterThan(0);

      const resEn = detectVoiceVisualIntent('Why does this error occur?');
      expect(resEn.hasVisualIntent).toBe(true);
      expect(resEn.category).toBe('error_diagnosis');
    });

    it('detects UI element queries', () => {
      const res = detectVoiceVisualIntent('这个按钮点了没反应');
      expect(res.hasVisualIntent).toBe(true);
      expect(res.category).toBe('ui_element_query');

      const resEn = detectVoiceVisualIntent('What is this button on the left?');
      expect(resEn.hasVisualIntent).toBe(true);
      expect(resEn.category).toBe('ui_element_query');
    });

    it('detects code inspection requests', () => {
      const res = detectVoiceVisualIntent('看一下这段代码有什么逻辑漏洞');
      expect(res.hasVisualIntent).toBe(true);
      expect(res.category).toBe('code_inspection');

      const resEn = detectVoiceVisualIntent('Review this code function please');
      expect(resEn.hasVisualIntent).toBe(true);
      expect(resEn.category).toBe('code_inspection');
    });

    it('detects general screen queries and deictic references', () => {
      const res = detectVoiceVisualIntent('屏幕上显示的是什么内容');
      expect(res.hasVisualIntent).toBe(true);
      expect(res.category).toBe('general_screen');

      const resDeictic = detectVoiceVisualIntent('这里怎么填');
      expect(resDeictic.hasVisualIntent).toBe(true);
      expect(resDeictic.category).toBe('general_screen');
    });

    it('bypasses non-visual utterances safely', () => {
      const res1 = detectVoiceVisualIntent('明天天气怎么样');
      expect(res1.hasVisualIntent).toBe(false);
      expect(res1.category).toBe('none');

      const res2 = detectVoiceVisualIntent('帮我写一个快速排序算法');
      expect(res2.hasVisualIntent).toBe(false);
      expect(res2.category).toBe('none');

      const res3 = detectVoiceVisualIntent('');
      expect(res3.hasVisualIntent).toBe(false);
      expect(res3.category).toBe('none');
    });
  });
});

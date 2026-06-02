import { describe, it, expect } from 'vitest';
import { classifyVisionIntent } from '@/hooks/useVisionIntent';

describe('useVisionIntent', () => {
  const getClassify = () => {
    return classifyVisionIntent;
  };

  describe('English patterns', () => {
    it('classifies "what do you see" as describe_scene', () => {
      const classify = getClassify();
      const result = classify('what do you see in front of me');
      expect(result.type).toBe('describe_scene');
      expect(result.needsVision).toBe(true);
    });

    it('classifies "read this text" as read_text', () => {
      const classify = getClassify();
      const result = classify('read this text for me');
      expect(result.type).toBe('read_text');
      expect(result.needsVision).toBe(true);
    });

    it('classifies "what is this object" as identify_object', () => {
      const classify = getClassify();
      const result = classify('what is this thing');
      expect(result.type).toBe('identify_object');
      expect(result.needsVision).toBe(true);
    });

    it('classifies "what changed" as compare_change', () => {
      const classify = getClassify();
      const result = classify('what changed since last time');
      expect(result.type).toBe('compare_change');
      expect(result.needsVision).toBe(true);
    });
  });

  describe('Chinese patterns', () => {
    it('classifies "你看到了什么" as describe_scene', () => {
      const classify = getClassify();
      const result = classify('你看到了什么');
      expect(result.type).toBe('describe_scene');
      expect(result.needsVision).toBe(true);
    });

    it('classifies "帮我读一下这个文字" as read_text', () => {
      const classify = getClassify();
      const result = classify('帮我读一下这个文字');
      expect(result.type).toBe('read_text');
      expect(result.needsVision).toBe(true);
    });

    it('classifies "这是什么东西" as identify_object', () => {
      const classify = getClassify();
      const result = classify('这是什么东西');
      expect(result.type).toBe('identify_object');
      expect(result.needsVision).toBe(true);
    });
  });

  describe('Chinese compare_change', () => {
    it('classifies "有什么变化" as compare_change', () => {
      const classify = getClassify();
      const result = classify('有什么变化');
      expect(result.type).toBe('compare_change');
      expect(result.needsVision).toBe(true);
    });
  });

  describe('text-only patterns', () => {
    it('classifies pure greeting as none', () => {
      const classify = getClassify();
      const result = classify('hello how are you');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });

    it('classifies "写一首诗" as none', () => {
      const classify = getClassify();
      const result = classify('写一首诗');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });

    it('classifies weather query as none', () => {
      const classify = getClassify();
      const result = classify('what is the weather today');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });

    it('classifies "翻译一下" as none (text_only pattern)', () => {
      const classify = getClassify();
      const result = classify('翻译一下这段话');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });

    it('classifies "summarize" as none (text_only pattern)', () => {
      const classify = getClassify();
      const result = classify('summarize this article');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });
  });

  describe('text-only patterns (code group)', () => {
    it('classifies "生成代码" as none (text_only pattern)', () => {
      const classify = getClassify();
      const result = classify('帮我生成代码');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
      expect(result.confidence).toBe(0.95);
    });

    it('classifies "generate code" as none (text_only pattern)', () => {
      const classify = getClassify();
      const result = classify('generate code for sorting');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });

    it('classifies "debug this" as none (text_only pattern)', () => {
      const classify = getClassify();
      const result = classify('debug this function please');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });
  });

  describe('confidence values', () => {
    it('returns confidence 0.6 for unmatched generic input', () => {
      const classify = getClassify();
      const result = classify('hello how are you');
      expect(result.confidence).toBe(0.6);
      expect(result.reason).toBe('no visual cue detected');
    });

    it('returns confidence 0.92 for matched vision rules', () => {
      const classify = getClassify();
      const result = classify('what do you see');
      expect(result.confidence).toBe(0.92);
    });

    it('returns confidence 1 for empty input', () => {
      const classify = getClassify();
      const result = classify('');
      expect(result.confidence).toBe(1);
      expect(result.reason).toBe('empty or text-only input');
    });
  });

  describe('edge cases', () => {
    it('classifies empty string as none', () => {
      const classify = getClassify();
      const result = classify('');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });

    it('classifies whitespace-only as none', () => {
      const classify = getClassify();
      const result = classify('   ');
      expect(result.type).toBe('none');
      expect(result.needsVision).toBe(false);
    });
  });
});

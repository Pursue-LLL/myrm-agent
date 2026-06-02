import { describe, it, expect } from 'vitest';
import { extractSpeakableSegments } from '@/hooks/useVoiceSession';

describe('extractSpeakableSegments', () => {
  it('returns empty array for empty input', () => {
    expect(extractSpeakableSegments('')).toEqual([]);
  });

  it('returns single segment without sentence terminator', () => {
    expect(extractSpeakableSegments('hello world')).toEqual(['hello world']);
  });

  it('splits on English sentence boundaries', () => {
    expect(extractSpeakableSegments('Hello world. How are you? I am fine!')).toEqual([
      'Hello world.',
      'How are you?',
      'I am fine!',
    ]);
  });

  it('splits on Chinese sentence boundaries', () => {
    expect(extractSpeakableSegments('你好。今天天气真好！吃了吗？')).toEqual(['你好。', '今天天气真好！', '吃了吗？']);
  });

  it('splits on newlines', () => {
    expect(extractSpeakableSegments('line one\nline two')).toEqual(['line one', 'line two']);
  });

  it('preserves trailing fragment without terminator', () => {
    expect(extractSpeakableSegments('First sentence. trailing fragment')).toEqual([
      'First sentence.',
      'trailing fragment',
    ]);
  });

  it('skips empty segments produced by consecutive terminators', () => {
    expect(extractSpeakableSegments('A!! B?? C..')).toEqual(['A!', 'B?', 'C.']);
  });

  it('trims whitespace around segments', () => {
    expect(extractSpeakableSegments('  hello.   world.  ')).toEqual(['hello.', 'world.']);
  });

  it('handles mixed language and punctuation', () => {
    expect(extractSpeakableSegments('Hello 你好。Mixed sentence! 再问一次?')).toEqual([
      'Hello 你好。',
      'Mixed sentence!',
      '再问一次?',
    ]);
  });
});

import { describe, expect, it } from 'vitest';
import { isStopCommand, normalizeVoiceCommand } from '@/hooks/voice/voiceCommands';

describe('voiceCommands', () => {
  it('matches stop commands across languages', () => {
    expect(isStopCommand('stop')).toBe(true);
    expect(isStopCommand('  STOP!  ')).toBe(true);
    expect(isStopCommand('停止')).toBe(true);
    expect(isStopCommand('停。')).toBe(true);
    expect(isStopCommand('quit')).toBe(true);
    expect(isStopCommand('退出')).toBe(true);
  });

  it('never matches mid-sentence dictation', () => {
    expect(isStopCommand('')).toBe(false);
    expect(isStopCommand('please stop that')).toBe(false);
    expect(isStopCommand('停一下')).toBe(false);
    expect(isStopCommand('stopwatch')).toBe(false);
  });

  it('normalizes case and trailing punctuation', () => {
    expect(normalizeVoiceCommand('  Stop... ')).toBe('stop');
  });
});

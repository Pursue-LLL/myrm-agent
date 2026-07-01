import { describe, it, expect } from 'vitest';
import { formatAppshotMessage } from '../FlowPadModalParts';
import type { FlowPadCapture } from '@/store/useFlowPadStore';

describe('formatAppshotMessage', () => {
  it('returns empty string for no captures', () => {
    expect(formatAppshotMessage([])).toBe('');
  });

  it('formats basic capture without selectedText', () => {
    const captures: FlowPadCapture[] = [{
      screenshot: '',
      windowTitle: 'VSCode - main.rs',
      extractedText: 'fn main() {}',
      timestamp: Date.now(),
    }];
    const result = formatAppshotMessage(captures);
    expect(result).toContain('[Appshot Context]');
    expect(result).toContain('**VSCode - main.rs**');
    expect(result).toContain('fn main() {}');
    expect(result).not.toContain('[Selected Context - Priority]');
  });

  it('prioritizes selectedText when present', () => {
    const captures: FlowPadCapture[] = [{
      screenshot: '',
      windowTitle: 'VSCode - main.rs',
      extractedText: 'fn main() { let x = 1; let y = 2; }',
      selectedText: 'let x = 1',
      timestamp: Date.now(),
    }];
    const result = formatAppshotMessage(captures);
    expect(result).toContain('[Selected Context - Priority]');
    expect(result).toContain('let x = 1');
    expect(result).toContain('fn main()');
  });

  it('truncates extractedText to 2000 chars when selectedText present', () => {
    const longText = 'a'.repeat(3000);
    const captures: FlowPadCapture[] = [{
      screenshot: '',
      windowTitle: 'Test',
      extractedText: longText,
      selectedText: 'selected',
      timestamp: Date.now(),
    }];
    const result = formatAppshotMessage(captures);
    expect(result).toContain('...(truncated)');
    expect(result.indexOf(longText)).toBe(-1);
  });

  it('does not truncate extractedText when no selectedText', () => {
    const text = 'b'.repeat(3000);
    const captures: FlowPadCapture[] = [{
      screenshot: '',
      windowTitle: 'Test',
      extractedText: text,
      timestamp: Date.now(),
    }];
    const result = formatAppshotMessage(captures);
    expect(result).not.toContain('...(truncated)');
  });

  it('ignores whitespace-only selectedText', () => {
    const captures: FlowPadCapture[] = [{
      screenshot: '',
      windowTitle: 'Test',
      extractedText: 'some text',
      selectedText: '   ',
      timestamp: Date.now(),
    }];
    const result = formatAppshotMessage(captures);
    expect(result).not.toContain('[Selected Context - Priority]');
  });
});

import { describe, it, expect } from 'vitest';
import { parseModelViewport } from '../replay/viewportParser';

describe('parseModelViewport', () => {
  it('returns empty summary for null or empty input', () => {
    expect(parseModelViewport(null)).toEqual({
      messages: [],
      totalMessages: 0,
      hasSystemPrompt: false,
      userMessageCount: 0,
      toolCallCount: 0,
      isGloballyTruncated: false,
      truncatedCharsCount: 0,
    });

    expect(parseModelViewport('   ')).toEqual({
      messages: [],
      totalMessages: 0,
      hasSystemPrompt: false,
      userMessageCount: 0,
      toolCallCount: 0,
      isGloballyTruncated: false,
      truncatedCharsCount: 0,
    });
  });

  it('correctly parses structured prompt preview with multiple roles', () => {
    const raw = `[system] You are an expert AI assistant.
Always think carefully.
[user] Help me refactor the database query.
[assistant] I will inspect the schema first.
[tool] {"table": "users", "count": 42}`;

    const parsed = parseModelViewport(raw);
    expect(parsed.totalMessages).toBe(4);
    expect(parsed.hasSystemPrompt).toBe(true);
    expect(parsed.userMessageCount).toBe(1);
    expect(parsed.toolCallCount).toBe(1);
    expect(parsed.isGloballyTruncated).toBe(false);

    expect(parsed.messages[0]).toEqual({
      id: 'vp-msg-0',
      role: 'system',
      content: 'You are an expert AI assistant.\nAlways think carefully.',
    });

    expect(parsed.messages[1]).toEqual({
      id: 'vp-msg-1',
      role: 'user',
      content: 'Help me refactor the database query.',
    });

    expect(parsed.messages[2]).toEqual({
      id: 'vp-msg-2',
      role: 'assistant',
      content: 'I will inspect the schema first.',
    });

    expect(parsed.messages[3]).toEqual({
      id: 'vp-msg-3',
      role: 'tool',
      content: '{"table": "users", "count": 42}',
    });
  });

  it('handles truncation notices from llm_observability.py', () => {
    const raw = `[system] Base prompt
[user] Long query
... [truncated 1500 chars]`;

    const parsed = parseModelViewport(raw);
    expect(parsed.isGloballyTruncated).toBe(true);
    expect(parsed.truncatedCharsCount).toBe(1500);
    expect(parsed.totalMessages).toBe(2);
    expect(parsed.messages[1].content).toBe('Long query');
  });
});

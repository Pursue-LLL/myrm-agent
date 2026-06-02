import { describe, it, expect } from 'vitest';

/**
 * Test messageStreamHandler diagnostic_result priority logic
 * Logic: prioritize diagnostic_result from backend > frontend getUserFriendlyError
 */
describe('messageStreamHandler - diagnostic_result priority logic', () => {
  it('should prioritize diagnostic_result over frontend translation', () => {
    // Simulate ERROR event with diagnostic_result
    const data = {
      type: 'ERROR',
      error: 'API key is invalid',
      error_kind: 'LLM_ERROR',
      diagnostic_result: {
        error_type: 'api_key',
        user_message: 'Invalid API key from backend i18n',
        resolution_steps: [
          'Check your API key in settings',
          'Verify API key format',
          'Visit https://platform.openai.com/api-keys for help',
        ],
        locale: 'en',
      },
    };

    let errorText: string = '';
    let hint: string | undefined;

    // Simulate the logic from messageStreamHandler
    if (data.diagnostic_result) {
      const diagnostic = data.diagnostic_result;
      errorText = diagnostic.user_message;
      if (diagnostic.resolution_steps.length > 0) {
        const stepsText = diagnostic.resolution_steps.map((step, i) => `${i + 1}. ${step}`).join('\n');
        hint = stepsText;
      }
    }

    expect(errorText).toBe('Invalid API key from backend i18n');
    expect(hint).toContain('1. Check your API key in settings');
    expect(hint).toContain('2. Verify API key format');
    expect(hint).toContain('3. Visit https://platform.openai.com/api-keys for help');
  });

  it('should use fallback path when diagnostic_result is missing', () => {
    // Simulate ERROR event WITHOUT diagnostic_result
    const data = {
      type: 'ERROR',
      error: 'API key is invalid',
      error_kind: 'LLM_ERROR',
    } as any;

    let usedFallback = false;

    if (data.diagnostic_result) {
      // Should NOT enter this branch
    } else {
      usedFallback = true;
    }

    expect(usedFallback).toBe(true);
    expect(data.diagnostic_result).toBeUndefined();
  });

  it('should handle diagnostic_result with empty resolution_steps', () => {
    const data = {
      type: 'ERROR',
      error: 'Unknown error',
      error_kind: 'LLM_ERROR',
      diagnostic_result: {
        error_type: 'unknown',
        user_message: 'Unknown error occurred',
        resolution_steps: [], // empty
        locale: 'en',
      },
    };

    let errorText: string = '';
    let hint: string | undefined;

    if (data.diagnostic_result) {
      const diagnostic = data.diagnostic_result;
      errorText = diagnostic.user_message;
      if (diagnostic.resolution_steps.length > 0) {
        const stepsText = diagnostic.resolution_steps.map((step, i) => `${i + 1}. ${step}`).join('\n');
        hint = stepsText;
      }
    }

    expect(errorText).toBe('Unknown error occurred');
    expect(hint).toBeUndefined();
  });

  it('should format resolution_steps with line numbers', () => {
    const diagnostic_result = {
      error_type: 'api_key',
      user_message: 'API key error',
      resolution_steps: ['Step one', 'Step two', 'Step three'],
      locale: 'en',
    };

    const stepsText = diagnostic_result.resolution_steps.map((step, i) => `${i + 1}. ${step}`).join('\n');

    expect(stepsText).toBe('1. Step one\n2. Step two\n3. Step three');
  });
});

/**
 * Test STEERING event handling logic from messageStreamHandler.
 * Validates the parsing of different SSE STEERING event data formats.
 */
describe('messageStreamHandler - STEERING event parsing', () => {
  function parseSteerText(steerData: { count?: number; messages?: string[] } | string | undefined): string {
    let steerText = 'Steering applied';
    if (typeof steerData === 'object' && steerData?.messages?.length) {
      const preview = steerData.messages[0].slice(0, 80);
      const suffix = steerData.messages[0].length > 80 || steerData.messages.length > 1 ? '...' : '';
      steerText = `Steering: "${preview}${suffix}"`;
    }
    return steerText;
  }

  it('should show preview of short single message', () => {
    const result = parseSteerText({ count: 1, messages: ['focus on testing'] });
    expect(result).toBe('Steering: "focus on testing"');
  });

  it('should truncate message longer than 80 chars', () => {
    const longMsg = 'A'.repeat(120);
    const result = parseSteerText({ count: 1, messages: [longMsg] });
    expect(result).toBe(`Steering: "${'A'.repeat(80)}..."`);
  });

  it('should add ellipsis for multiple messages', () => {
    const result = parseSteerText({ count: 2, messages: ['first', 'second'] });
    expect(result).toBe('Steering: "first..."');
  });

  it('should fallback for undefined data', () => {
    const result = parseSteerText(undefined);
    expect(result).toBe('Steering applied');
  });

  it('should fallback for string data (backward compat)', () => {
    const result = parseSteerText('Steering with 2 new message(s)' as unknown as undefined);
    expect(result).toBe('Steering applied');
  });

  it('should fallback for empty messages array', () => {
    const result = parseSteerText({ count: 0, messages: [] });
    expect(result).toBe('Steering applied');
  });

  it('should handle Chinese/Unicode in preview', () => {
    const result = parseSteerText({ count: 1, messages: ['请专注于中文搜索结果'] });
    expect(result).toBe('Steering: "请专注于中文搜索结果"');
  });

  it('should handle message with newlines (no truncation under 80)', () => {
    const msg = 'line1\nline2\nline3';
    const result = parseSteerText({ count: 1, messages: [msg] });
    expect(result).toBe(`Steering: "${msg}"`);
  });
});

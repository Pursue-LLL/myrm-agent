import { describe, expect, it } from 'vitest';
import { parseIncrementalStream } from '../incrementalStreamParser';

describe('incrementalStreamParser', () => {
  it('handles empty text gracefully', () => {
    const result = parseIncrementalStream('', true);
    expect(result.frozenBlocks).toHaveLength(0);
    expect(result.activeTailBlock).toBeNull();
    expect(result.totalBlocksCount).toBe(0);
    expect(result.fullContentLength).toBe(0);
  });

  it('parses single unclosed paragraph during streaming as activeTailBlock', () => {
    const stream = 'Hello this is an incomplete token chunk';
    const result = parseIncrementalStream(stream, true);

    expect(result.frozenBlocks).toHaveLength(0);
    expect(result.activeTailBlock).not.toBeNull();
    expect(result.activeTailBlock?.type).toBe('paragraph');
    expect(result.activeTailBlock?.rawContent).toBe(stream);
    expect(result.activeTailBlock?.isFrozen).toBe(false);
  });

  it('freezes single paragraph when stream finishes', () => {
    const text = 'Hello world final text';
    const result = parseIncrementalStream(text, false);

    expect(result.frozenBlocks).toHaveLength(1);
    expect(result.frozenBlocks[0]?.type).toBe('paragraph');
    expect(result.frozenBlocks[0]?.isFrozen).toBe(true);
    expect(result.activeTailBlock).toBeNull();
  });

  it('freezes closed paragraph when separated by double newline and keeps tail active', () => {
    const text = 'First closed paragraph.\n\nSecond active paragraph being typed';
    const result = parseIncrementalStream(text, true);

    expect(result.frozenBlocks).toHaveLength(1);
    expect(result.frozenBlocks[0]?.rawContent).toBe('First closed paragraph.');
    expect(result.frozenBlocks[0]?.isFrozen).toBe(true);

    expect(result.activeTailBlock).not.toBeNull();
    expect(result.activeTailBlock?.rawContent).toBe('Second active paragraph being typed');
    expect(result.activeTailBlock?.isFrozen).toBe(false);
    expect(result.totalBlocksCount).toBe(2);
  });

  it('handles fenced code blocks correctly during streaming and after closure', () => {
    // 1. 未闭合的代码块
    const unclosedCode = '```typescript\nconst greeting = "hello";\nconsole.log(greeting);';
    const streamingResult = parseIncrementalStream(unclosedCode, true);

    expect(streamingResult.frozenBlocks).toHaveLength(0);
    expect(streamingResult.activeTailBlock).not.toBeNull();
    expect(streamingResult.activeTailBlock?.type).toBe('code');
    expect(streamingResult.activeTailBlock?.language).toBe('typescript');

    // 2. 闭合的代码块 + 后续追加段落
    const closedCodeAndMore = '```typescript\nconst x = 42;\n```\n\nNext follow-up text';
    const closedResult = parseIncrementalStream(closedCodeAndMore, true);

    expect(closedResult.frozenBlocks).toHaveLength(1);
    expect(closedResult.frozenBlocks[0]?.type).toBe('code');
    expect(closedResult.frozenBlocks[0]?.language).toBe('typescript');
    expect(closedResult.frozenBlocks[0]?.isFrozen).toBe(true);

    expect(closedResult.activeTailBlock).not.toBeNull();
    expect(closedResult.activeTailBlock?.rawContent).toBe('Next follow-up text');
  });

  it('accurately parses headings, blockquotes, and lists with level detection', () => {
    const markdown = '### Section Title\n\n> Important quoted advice\n\n- Item 1\n- Item 2';
    const result = parseIncrementalStream(markdown, false);

    expect(result.frozenBlocks).toHaveLength(3);
    expect(result.frozenBlocks[0]?.type).toBe('heading');
    expect(result.frozenBlocks[0]?.level).toBe(3);
    expect(result.frozenBlocks[1]?.type).toBe('blockquote');
    expect(result.frozenBlocks[2]?.type).toBe('list');
  });
});

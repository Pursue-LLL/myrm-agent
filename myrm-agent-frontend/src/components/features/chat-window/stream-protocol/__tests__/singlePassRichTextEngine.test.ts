import { describe, it, expect } from 'vitest';
import {
  parseSinglePassRichSpans,
  parseStreamToTypedBlocks,
  benchmarkSinglePassParser,
} from '../singlePassRichTextEngine';

describe('singlePassRichTextEngine', () => {
  it('parses plain text into a single plain span', () => {
    const spans = parseSinglePassRichSpans('Hello World, this is normal text.');
    expect(spans).toHaveLength(1);
    expect(spans[0].type).toBe('plain');
    expect(spans[0].text).toBe('Hello World, this is normal text.');
  });

  it('parses bold and inline code spans in a single pass', () => {
    const raw = 'This is **bold text** and `inline_code()` function.';
    const spans = parseSinglePassRichSpans(raw);

    expect(spans.some((s) => s.type === 'bold' && s.text === 'bold text')).toBe(true);
    expect(spans.some((s) => s.type === 'inline_code' && s.text === 'inline_code()')).toBe(true);
  });

  it('parses ANSI color escape codes into colorized spans without leaking escapes', () => {
    const rawWithAnsi = '\x1b[32m[SUCCESS]\x1b[0m Operation finished with \x1b[31merror\x1b[0m';
    const spans = parseSinglePassRichSpans(rawWithAnsi);

    const successSpan = spans.find((s) => s.type === 'ansi_color' && s.text === '[SUCCESS]');
    expect(successSpan).toBeDefined();
    expect(successSpan?.colorClass).toBe('text-emerald-400');

    const errorSpan = spans.find((s) => s.type === 'ansi_color' && s.text === 'error');
    expect(errorSpan).toBeDefined();
    expect(errorSpan?.colorClass).toBe('text-red-400');
  });

  it('splits stream text into typed paragraph and code blocks', () => {
    const streamContent = `Here is some intro text.

\`\`\`typescript
const a = 1;
console.log(a);
\`\`\`

Here is trailing text.`;

    const blocks = parseStreamToTypedBlocks(streamContent);
    expect(blocks.length).toBeGreaterThanOrEqual(3);

    const codeBlock = blocks.find((b) => b.type === 'code_block');
    expect(codeBlock).toBeDefined();
    expect(codeBlock?.language).toBe('typescript');
    expect(codeBlock?.isFinalized).toBe(true);
    expect(codeBlock?.spans[0].text).toContain('const a = 1;');
  });

  it('tolerates unclosed code block during active streaming', () => {
    const unclosedStream = `\`\`\`python\ndef run():\n  pass`;
    const blocks = parseStreamToTypedBlocks(unclosedStream);

    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe('code_block');
    expect(blocks[0].language).toBe('python');
    expect(blocks[0].isFinalized).toBe(false);
  });

  it('benchmarks single-pass parser throughput and memory', () => {
    const sample = 'Benchmark sample text '.repeat(50);
    const metrics = benchmarkSinglePassParser(sample);

    expect(metrics.parseDurationMs).toBeGreaterThanOrEqual(0.01);
    expect(metrics.tokenCount).toBeGreaterThan(50);
    expect(metrics.throughputTokensPerSec).toBeGreaterThan(0);
    expect(metrics.estimatedCpuUsagePct).toBeLessThanOrEqual(15);
  });
});

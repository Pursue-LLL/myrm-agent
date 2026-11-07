import { describe, expect, it } from 'vitest';

import { MAX_IMPORT_SIZE_MB, isImportFileTooLarge, readImportPayload } from '../memoryImportFile';

const MAX_BYTES = MAX_IMPORT_SIZE_MB * 1024 * 1024;

const fileOf = (name: string, content: string, size?: number): File => {
  const file = new File([content], name);
  if (size !== undefined) {
    Object.defineProperty(file, 'size', { value: size });
  }
  return file;
};

describe('isImportFileTooLarge', () => {
  it('allows a file exactly at the limit and rejects one byte more', () => {
    expect(isImportFileTooLarge(fileOf('a.json', '{}', MAX_BYTES))).toBe(false);
    expect(isImportFileTooLarge(fileOf('a.json', '{}', MAX_BYTES + 1))).toBe(true);
  });

  it('allows small files', () => {
    expect(isImportFileTooLarge(fileOf('a.json', '{}'))).toBe(false);
  });
});

describe('readImportPayload', () => {
  it('parses a JSON document and lets the server detect its source', async () => {
    await expect(readImportPayload(fileOf('export.json', '{"version":2,"data":{"a":[1]}}'), 'none')).resolves.toEqual({
      payload: { version: 2, data: { a: [1] } },
      source: 'auto',
    });
  });

  it('wraps the valid lines of a JSONL transcript and tags the Claude Code source', async () => {
    const content = '{"n":1}\n\n   \nnot json\n{"n":2}\n';

    await expect(readImportPayload(fileOf('session.jsonl', content), 'none')).resolves.toEqual({
      payload: { jsonl_lines: [{ n: 1 }, { n: 2 }], _source_hint: 'claude_code_jsonl' },
      source: 'claude_code_jsonl',
    });
  });

  it('fails with the given message when no JSONL line is valid', async () => {
    await expect(readImportPayload(fileOf('session.jsonl', 'oops\n{broken'), 'no valid lines')).rejects.toThrow(
      'no valid lines',
    );
    await expect(readImportPayload(fileOf('empty.jsonl', ''), 'no valid lines')).rejects.toThrow('no valid lines');
  });

  it('fails on a JSON file that cannot be parsed', async () => {
    await expect(readImportPayload(fileOf('export.json', '{ nope'), 'none')).rejects.toBeInstanceOf(SyntaxError);
  });

  it('treats only the .jsonl extension as line-delimited', async () => {
    await expect(readImportPayload(fileOf('export.jsonl.json', '{"a":1}'), 'none')).resolves.toMatchObject({
      source: 'auto',
    });
  });
});

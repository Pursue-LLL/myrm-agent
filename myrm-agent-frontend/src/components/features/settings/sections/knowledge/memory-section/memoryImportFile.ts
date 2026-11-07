/**
 * [INPUT] @/services/memory/archive::MemoryImportSource (POS: 导入来源标识)
 * [OUTPUT] MAX_IMPORT_SIZE_MB / isImportFileTooLarge / readImportPayload: 导入文件的体积上限与文件到 dry-run 请求体的纯转换
 * [POS] 记忆导入的文件解析层（无 React）：.jsonl（Claude Code 会话）按行解析并跳过损坏行，其余文件按单个 JSON 文档解析。
 */

import type { MemoryImportSource } from '@/services/memory/archive';

export const MAX_IMPORT_SIZE_MB = 50;

export interface ImportPayload {
  payload: Record<string, unknown>;
  source: Extract<MemoryImportSource, 'auto' | 'claude_code_jsonl'>;
}

export function isImportFileTooLarge(file: File): boolean {
  return file.size > MAX_IMPORT_SIZE_MB * 1024 * 1024;
}

export async function readImportPayload(file: File, noValidLinesMessage: string): Promise<ImportPayload> {
  const text = await file.text();
  if (!file.name.endsWith('.jsonl')) {
    return { payload: JSON.parse(text) as Record<string, unknown>, source: 'auto' };
  }

  const lines: unknown[] = [];
  for (const line of text.split('\n')) {
    try {
      lines.push(JSON.parse(line));
    } catch {
      // Blank and malformed lines (streaming truncation, encoding issues) are skipped; the rest still imports.
    }
  }
  if (lines.length === 0) {
    throw new Error(noValidLinesMessage);
  }
  return { payload: { jsonl_lines: lines, _source_hint: 'claude_code_jsonl' }, source: 'claude_code_jsonl' };
}

/**
 * [INPUT]
 * @/services/memory::(ChunkSliceResponse, IncrementalIndexResponse, HydrateResponse, MarkdownChunkDTO)
 *
 * [OUTPUT]
 * Constants: SAMPLE_MARKDOWN_DOCUMENTS, FALLBACK_SLICE_RESPONSE,
 *            FALLBACK_INCREMENTAL_RESPONSE, FALLBACK_HYDRATE_RESPONSE
 *
 * [POS]
 * Fallback and preset sample data for Markdown Sliding Window Chunker UI components.
 * Strictly typed with zero `any`. Single file < 160 lines.
 */

import type {
  ChunkSliceResponse,
  HydrateResponse,
  IncrementalIndexResponse,
  MarkdownChunkDTO,
} from '@/services/memory';

export const SAMPLE_MARKDOWN_DOCUMENTS: Record<
  string,
  { label: string; path: string; initial: string; updated: string }
> = {
  memory_architecture: {
    label: '核心记忆架构 (MEMORY.md)',
    path: 'docs/MEMORY.md',
    initial: `# 长期记忆体系架构总览

本规范定义智能体在全周期持久化交互中的事实沉淀、偏好提取与技能经验复用机制。
系统必须保障多轮会话之间的语义一致性与低延迟召回。

## 滑动窗口切片标准

当长文档进入向量索引管线时，传统的固定字数切块会导致自然语句在中间被生硬截断。
滑动窗口切片策略基于语义段落划分，目标容量为 400 token，并维持 80 token 的相邻重叠预算。
跨块重叠确保即便关键实体位于分界边缘，召回时也能保留完整主谓宾语境。

\`\`\`typescript
interface SemanticChunk {
  chunk_id: string;
  start_line: number;
  end_line: number;
  content_hash: string;
}
\`\`\`

## 增量索引与内容哈希

每次记忆文档发生保存或追加时，系统通过计算 Chunk 级别的确定性 SHA-256 哈希比对前序版本。
仅对新增或发生实质变更的分块触发远程 Embedding API 调用，对未变动分块实现零开销复用。
实测可为大型记忆库节约 80% 以上的模型调用 Token 开销。`,
    updated: `# 长期记忆体系架构总览

本规范定义智能体在全周期持久化交互中的事实沉淀、偏好提取与技能经验复用机制。
系统必须保障多轮会话之间的语义一致性与低延迟召回。

## 滑动窗口切片标准

当长文档进入向量索引管线时，传统的固定字数切块会导致自然语句在中间被生硬截断。
滑动窗口切片策略基于语义段落划分，目标容量为 400 token，并维持 80 token 的相邻重叠预算。
跨块重叠确保即便关键实体位于分界边缘，召回时也能保留完整主谓宾语境。

\`\`\`typescript
interface SemanticChunk {
  chunk_id: string;
  start_line: number;
  end_line: number;
  content_hash: string;
}
\`\`\`

## 增量索引与内容哈希

每次记忆文档发生保存或追加时，系统通过计算 Chunk 级别的确定性 SHA-256 哈希比对前序版本。
仅对新增或发生实质变更的分块触发远程 Embedding API 调用，对未变动分块实现零开销复用。
实测可为大型记忆库节约 80% 以上的模型调用 Token 开销。

## 实时水合与回溯指针 (新增段落)

每个向量切片均持久化精确的起始与结束行号指针。
在检索引擎命中该分块后，系统可按需直接回溯源文档并扩展周边 3~5 行上下文，消除片段孤岛感。`,
  },
};

export const FALLBACK_CHUNKS: MarkdownChunkDTO[] = [
  {
    chunk_id: 'chk_demo_01',
    source_path: 'docs/MEMORY.md',
    start_line: 1,
    end_line: 7,
    char_start: 0,
    char_end: 245,
    text: '# 长期记忆体系架构总览\n\n本规范定义智能体在全周期持久化交互中的事实沉淀、偏好提取与技能经验复用机制。\n系统必须保障多轮会话之间的语义一致性与低延迟召回。',
    chunk_hash: 'a1b2c3d4e5f60718',
    token_estimate: 72,
    is_truncated: false,
  },
  {
    chunk_id: 'chk_demo_02',
    source_path: 'docs/MEMORY.md',
    start_line: 8,
    end_line: 22,
    char_start: 246,
    char_end: 630,
    text: '## 滑动窗口切片标准\n\n当长文档进入向量索引管线时，传统的固定字数切块会导致自然语句在中间被生硬截断。\n滑动窗口切片策略基于语义段落划分，目标容量为 400 token，并维持 80 token 的相邻重叠预算。\n\n```typescript\ninterface SemanticChunk {\n  chunk_id: string;\n  start_line: number;\n  end_line: number;\n}\n```',
    chunk_hash: 'b2c3d4e5f6071829',
    token_estimate: 128,
    is_truncated: false,
  },
  {
    chunk_id: 'chk_demo_03',
    source_path: 'docs/MEMORY.md',
    start_line: 23,
    end_line: 32,
    char_start: 631,
    char_end: 980,
    text: '## 增量索引与内容哈希\n\n每次记忆文档发生保存或追加时，系统通过计算 Chunk 级别的确定性 SHA-256 哈希比对前序版本。\n仅对新增或发生实质变更的分块触发远程 Embedding API 调用，对未变动分块实现零开销复用。',
    chunk_hash: 'c3d4e5f60718293a',
    token_estimate: 98,
    is_truncated: false,
  },
];

export const FALLBACK_SLICE_RESPONSE: ChunkSliceResponse = {
  source_path: 'docs/MEMORY.md',
  total_chunks: FALLBACK_CHUNKS.length,
  chunks: FALLBACK_CHUNKS,
};

export const FALLBACK_INCREMENTAL_RESPONSE: IncrementalIndexResponse = {
  report: {
    source_path: 'docs/MEMORY.md',
    total_chunks: 4,
    reused_chunks: 3,
    changed_chunks: 1,
    deleted_chunks: 0,
    token_savings_pct: 74.8,
    status: 'partially_updated',
    timestamp: '2026-10-08T06:30:00Z',
  },
  chunks: [
    ...FALLBACK_CHUNKS,
    {
      chunk_id: 'chk_demo_04',
      source_path: 'docs/MEMORY.md',
      start_line: 33,
      end_line: 40,
      char_start: 981,
      char_end: 1220,
      text: '## 实时水合与回溯指针 (新增段落)\n\n每个向量切片均持久化精确的起始与结束行号指针。系统可按需直接回溯源文档并扩展周边 3~5 行上下文。',
      chunk_hash: 'd4e5f60718293a4b',
      token_estimate: 65,
      is_truncated: false,
    },
  ],
};

export const FALLBACK_HYDRATE_RESPONSE: HydrateResponse = {
  hydrated_text:
    '-- [前置上下文 L6-L7] --\n系统必须保障多轮会话之间的语义一致性与低延迟召回。\n\n## 滑动窗口切片标准\n当长文档进入向量索引管线时，传统的固定字数切块会导致自然语句在中间被生硬截断。\n滑动窗口切片策略基于语义段落划分，目标容量为 400 token，并维持 80 token 的相邻重叠预算。\n\n-- [后置上下文 L23-L24] --\n## 增量索引与内容哈希',
  window_lines: 2,
  start_line: 8,
  end_line: 22,
};

import { describe, it, expect } from 'vitest';
import { parseCompactionEntry } from '../compactionParser';
import type { ArchivedChatMessage } from '@/services/chat';
import type { LastCompactionMeta } from '@/store/chat/types';

describe('compactionParser', () => {
  it('parses structured sections from markdown correctly', () => {
    const rawMarkdown = `
### 目标
完成前端 UX 路线图 Item 27 记忆结晶压缩卡片。

### 进展
已实现类型定义、时光机抽屉与单元测试。

### 核心决策
- 采用 5 段式结构化卡片
- 只读时光机原地平滑抽屉展开

### 下一步
- 挂载至宿主视图
- 推进 Item 28
`;

    const meta: LastCompactionMeta = {
      tokensSaved: 12500,
      snapshotPath: 'snapshots/step27.json',
      exactAnchors: {
        filePaths: ['src/fileA.ts', 'src/fileB.ts'],
      },
    };

    const mockMessages: ArchivedChatMessage[] = [
      { id: 'msg-1', role: 'user', content: 'hello', created_at: '2026-08-31T10:00:00Z' },
    ];

    const result = parseCompactionEntry(rawMarkdown, meta, mockMessages);

    expect(result.id).toBe('snapshots/step27.json');
    expect(result.savedTokens).toBe(12500);
    expect(result.compactedMessagesCount).toBe(1);
    expect(result.goal).toContain('完成前端 UX 路线图');
    expect(result.progress).toContain('已实现类型定义');
    expect(result.keyDecisions).toHaveLength(2);
    expect(result.nextSteps).toHaveLength(2);
    expect(result.filesTouched).toEqual(['src/fileA.ts', 'src/fileB.ts']);
    expect(result.originalMessages).toHaveLength(1);
    expect(result.originalMessages[0]).toMatchObject({ id: 'msg-1', content: 'hello', timestamp: '2026-08-31T10:00:00Z' });
  });

  it('handles unstructured fallback gracefully', () => {
    const rawMarkdown = 'Simple single sentence summary without headings.';
    const result = parseCompactionEntry(rawMarkdown);

    expect(result.goal).toBe('Simple single sentence summary without headings.');
    expect(result.savedTokens).toBe(0);
    expect(result.keyDecisions.length).toBeGreaterThan(0);
    expect(result.nextSteps.length).toBeGreaterThan(0);
    expect(result.originalMessages).toEqual([]);
    expect(result.filesTouched).toEqual([]);
    expect(result.compactedMessagesCount).toBe(0);
  });
});

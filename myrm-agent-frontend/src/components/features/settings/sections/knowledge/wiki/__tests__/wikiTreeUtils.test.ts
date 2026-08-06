import { describe, it, expect } from 'vitest';
import { countDescendantItems, extractSourceChatIdFromFrontmatter, filterFolderNodes, resolveCreateParentFolder } from '../wikiTreeUtils';
import type { TreeNode } from '@/services/wikiService';

const sampleTree: TreeNode[] = [
  {
    id: 'research',
    name: 'research',
    is_dir: true,
    children: [
      { id: 'research/paper-a', name: 'paper-a', is_dir: false },
      {
        id: 'research/ai',
        name: 'ai',
        is_dir: true,
        children: [{ id: 'research/ai/gpt', name: 'gpt', is_dir: false }],
      },
    ],
  },
  { id: 'notes', name: 'notes', is_dir: false },
];

describe('wikiTreeUtils', () => {
  it('filters folder nodes only', () => {
    const folders = filterFolderNodes(sampleTree);
    expect(folders).toHaveLength(1);
    expect(folders[0].id).toBe('research');
    expect(folders[0].children?.[0].id).toBe('research/ai');
  });

  it('counts descendant items inside a folder', () => {
    expect(countDescendantItems(sampleTree, 'research')).toBe(3);
    expect(countDescendantItems(sampleTree, 'missing')).toBe(0);
  });

  it('resolves create parent from focused node', () => {
    expect(resolveCreateParentFolder('research/ai', true)).toBe('research/ai');
    expect(resolveCreateParentFolder('research/paper-a', false)).toBe('research');
    expect(resolveCreateParentFolder(undefined, undefined)).toBeNull();
  });

  it('extracts source_chat from frontmatter with quoted and unquoted values', () => {
    const unquoted = '---\nsource_chat: chat-abc\n---\n# body';
    const doubleQuoted = '---\nsource_chat: "chat:colon-id"\n---\n# body';
    const singleQuoted = "---\nsource_chat: 'chat-single'\n---\n# body";
    expect(extractSourceChatIdFromFrontmatter(unquoted)).toBe('chat-abc');
    expect(extractSourceChatIdFromFrontmatter(doubleQuoted)).toBe('chat:colon-id');
    expect(extractSourceChatIdFromFrontmatter(singleQuoted)).toBe('chat-single');
    expect(extractSourceChatIdFromFrontmatter('no frontmatter')).toBeNull();
  });
});

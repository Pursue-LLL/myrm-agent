/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TreeNode } from '@/services/wikiService';

import { WikiFolderSelectTree } from '../WikiFolderSelectTree';

const DATA: TreeNode[] = [
  { id: 'research', name: 'Research', is_dir: true, children: [] },
  { id: 'notes', name: 'Notes', is_dir: true, children: [] },
];

function renderTree(selectedFolder: string | null = null) {
  const onSelectFolder = vi.fn();
  render(
    <WikiFolderSelectTree data={DATA} height={200} selectedFolder={selectedFolder} onSelectFolder={onSelectFolder} />,
  );
  return onSelectFolder;
}

describe('WikiFolderSelectTree', () => {
  it('renders each folder as a native button that selects it', () => {
    const onSelectFolder = renderTree();

    const folder = screen.getByRole('button', { name: 'Research' });
    expect(folder.tagName).toBe('BUTTON');
    expect(folder.getAttribute('type')).toBe('button');

    fireEvent.click(folder);
    expect(onSelectFolder).toHaveBeenCalledWith('research');
  });

  it('highlights only the selected folder', () => {
    renderTree('notes');

    expect(screen.getByRole('button', { name: 'Notes' }).className).toContain('bg-primary/20');
    expect(screen.getByRole('button', { name: 'Research' }).className).not.toContain('bg-primary/20');
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WikiConceptTree } from '../WikiConceptTree';
import type { TreeNode } from '@/services/wikiService';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/hooks/ui/useMediaQuery', () => ({ useIsMobile: () => false }));

const treeData: TreeNode[] = [
  { id: 'alpha', name: 'alpha', is_dir: false },
  { id: 'beta', name: 'beta', is_dir: false },
];

function renderTree(onSelectConcept = vi.fn(), onDelete = vi.fn()) {
  const treeRef = { current: null };
  render(
    <WikiConceptTree
      treeRef={treeRef}
      treeData={treeData}
      query=""
      treeHeight={200}
      isLoading={false}
      selectedConcept={null}
      isDeleting={null}
      onMove={vi.fn()}
      onSelectConcept={onSelectConcept}
      onRename={vi.fn()}
      onDelete={onDelete}
    />,
  );
  return { onSelectConcept, onDelete };
}

describe('WikiConceptTree activation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens a concept on mouse click exactly once', () => {
    const { onSelectConcept } = renderTree();
    fireEvent.click(screen.getByText('alpha'));
    expect(onSelectConcept).toHaveBeenCalledTimes(1);
    expect(onSelectConcept).toHaveBeenCalledWith('alpha');
  });

  it('opens the focused concept with the keyboard (arrow navigation + Space)', () => {
    const { onSelectConcept } = renderTree();
    const tree = screen.getByRole('tree');
    fireEvent.focus(tree);
    fireEvent.keyDown(tree, { key: 'ArrowDown' });
    fireEvent.keyDown(tree, { key: ' ' });
    expect(onSelectConcept).toHaveBeenCalledTimes(1);
    expect(['alpha', 'beta']).toContain(onSelectConcept.mock.calls[0][0]);
  });

  it('does not open the concept when a row action button is clicked', () => {
    const { onSelectConcept, onDelete } = renderTree();
    fireEvent.click(screen.getAllByLabelText('delete')[0]);
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onSelectConcept).not.toHaveBeenCalled();
  });
});

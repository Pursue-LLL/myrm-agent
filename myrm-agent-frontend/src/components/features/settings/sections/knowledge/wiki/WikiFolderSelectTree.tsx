'use client';

import { Folder } from 'lucide-react';
import { Tree } from 'react-arborist';
import type { TreeNode } from '@/services/wikiService';

interface WikiFolderSelectTreeProps {
  data: TreeNode[];
  height: number;
  selectedFolder: string | null;
  onSelectFolder: (folderId: string) => void;
}

export function WikiFolderSelectTree({ data, height, selectedFolder, onSelectFolder }: WikiFolderSelectTreeProps) {
  return (
    <Tree data={data} width="100%" height={height} rowHeight={32} indent={16}>
      {({ node, style }) => (
        <div
          style={style}
          className={`flex items-center gap-2 px-2 py-1 cursor-pointer rounded-md hover:bg-muted/50 transition-colors ${
            selectedFolder === node.id ? 'bg-primary/20 text-primary font-medium' : ''
          }`}
          onClick={() => onSelectFolder(node.id)}
        >
          <Folder className="w-4 h-4 shrink-0 text-primary" />
          <span className="truncate text-sm">{node.data.name}</span>
        </div>
      )}
    </Tree>
  );
}

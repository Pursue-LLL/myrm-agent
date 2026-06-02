'use client';

import type { TreeApi } from 'react-arborist';
import { Tree } from 'react-arborist';
import { useTranslations } from 'next-intl';
import { ChevronRight, ChevronDown, Folder, FileText, Edit2 } from 'lucide-react';
import { IconLoader, IconTrash } from '@/components/ui/icons/PremiumIcons';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { cn } from '@/lib/utils/classnameUtils';
import type { TreeNode } from '@/services/wikiService';
import type { Concept } from '@/services/wikiService';
import type { DeleteTarget } from './useWikiConceptsList';

interface WikiConceptTreeProps {
  treeRef: React.RefObject<TreeApi<TreeNode> | null>;
  treeData: TreeNode[];
  query: string;
  treeHeight: number;
  isLoading: boolean;
  selectedConcept: Concept | null;
  isDeleting: string | null;
  onMove: (args: { dragIds: string[]; parentId: string | null; index: number }) => void;
  onSelectConcept: (id: string) => void;
  onRename: (id: string, currentName: string, e?: React.MouseEvent) => void;
  onDelete: (target: DeleteTarget) => void;
}

export function WikiConceptTree({
  treeRef,
  treeData,
  query,
  treeHeight,
  isLoading,
  selectedConcept,
  isDeleting,
  onMove,
  onSelectConcept,
  onRename,
  onDelete,
}: WikiConceptTreeProps) {
  const t = useTranslations('settings.wiki.concepts');
  const isMobile = useIsMobile();

  if (isLoading) {
    return (
      <div className="flex justify-center p-8">
        <IconLoader className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (treeData.length === 0) {
    return <div className="text-center p-8 text-muted-foreground">{t('noResults')}</div>;
  }

  return (
    <Tree
      ref={treeRef}
      data={treeData}
      searchTerm={query}
      searchMatch={(node, term) => node.data.name.toLowerCase().includes(term.toLowerCase())}
      onMove={onMove}
      width="100%"
      height={treeHeight}
      rowHeight={32}
      indent={16}
      disableDrop={(args) => args.parentNode.data.is_dir === false}
    >
      {({ node, style, dragHandle }) => {
        const isSelected = selectedConcept?.name === node.id;

        return (
          <div
            style={style}
            ref={dragHandle}
            className={cn(
              'group flex items-center justify-between px-2 py-1 cursor-pointer hover:bg-muted/50 transition-colors',
              isSelected && 'bg-muted border-l-2 border-l-primary',
            )}
            onClick={(e) => {
              if ((e.target as HTMLElement).closest('[data-wiki-node-action]')) return;
              if (node.data.is_dir) {
                node.toggle();
              } else {
                void onSelectConcept(node.id);
              }
            }}
          >
            <div className="flex items-center gap-2 overflow-hidden pointer-events-none">
              {node.data.is_dir ? (
                node.isOpen ? (
                  <ChevronDown className="w-4 h-4 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground" />
                )
              ) : (
                <span className="w-4 shrink-0" />
              )}

              {node.data.is_dir ? (
                <Folder className="w-4 h-4 shrink-0 text-primary" />
              ) : (
                <FileText className="w-4 h-4 shrink-0 text-muted-foreground" />
              )}

              <span className="font-medium truncate text-sm">{node.data.name}</span>
            </div>

            <div
              data-wiki-node-action
              className={cn(
                'flex items-center gap-1 transition-opacity',
                isMobile ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
              )}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
            >
              <button
                type="button"
                aria-label={t('rename')}
                className="h-8 w-8 min-h-[32px] min-w-[32px] flex items-center justify-center rounded-full text-muted-foreground hover:text-primary hover:bg-primary/10"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onRename(node.id, node.data.name, e);
                }}
              >
                <Edit2 className="h-3 w-3 pointer-events-none" />
              </button>
              <button
                type="button"
                aria-label={t('delete')}
                className="h-8 w-8 min-h-[32px] min-w-[32px] flex items-center justify-center rounded-full text-destructive hover:bg-destructive/10"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDelete({ name: node.id, isDir: node.data.is_dir });
                }}
              >
                {isDeleting === node.id ? (
                  <IconLoader className="h-3 w-3 animate-spin pointer-events-none" />
                ) : (
                  <IconTrash className="h-3 w-3 pointer-events-none" />
                )}
              </button>
            </div>
          </div>
        );
      }}
    </Tree>
  );
}

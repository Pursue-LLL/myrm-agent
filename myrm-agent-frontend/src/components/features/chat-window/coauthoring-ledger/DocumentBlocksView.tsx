import React from 'react';
import { CollaboratorItem, DocumentBlockItem } from './types';

export interface DocumentBlocksViewProps {
  blocks: DocumentBlockItem[];
  collaborators: CollaboratorItem[];
  selectedBlockId: string;
  onSelectBlockId: (id: string) => void;
  editDraft: string;
  onChangeEditDraft: (val: string) => void;
  intentInput: string;
  onChangeIntentInput: (val: string) => void;
  isProcessing: boolean;
  onAcquireLease: (blockId: string) => void;
  onReleaseLease: (blockId: string) => void;
  onCommitEdit: () => void;
}

export const DocumentBlocksView: React.FC<DocumentBlocksViewProps> = ({
  blocks,
  collaborators,
  selectedBlockId,
  onSelectBlockId,
  editDraft,
  onChangeEditDraft,
  intentInput,
  onChangeIntentInput,
  isProcessing,
  onAcquireLease,
  onReleaseLease,
  onCommitEdit,
}) => {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Document Blocks</h4>
          {blocks.map((block) => {
            const isLocked = Boolean(block.leaseHolderId);
            const isSelected = block.blockId === selectedBlockId;
            const holder = collaborators.find((c) => c.collaboratorId === block.leaseHolderId);
            return (
              <button
                type="button"
                key={block.blockId}
                onClick={() => {
                  onSelectBlockId(block.blockId);
                  onChangeEditDraft(block.content);
                }}
                className={`w-full text-left p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                  isSelected
                    ? 'border-primary/60 bg-primary/5 shadow-xs'
                    : 'border-border/60 bg-muted/20 hover:border-border'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono font-medium text-foreground">{block.blockId}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground font-mono">
                      v{block.version}
                    </span>
                    {isLocked ? (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 font-mono">
                        🔒 {holder?.name || block.leaseHolderId}
                      </span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 font-mono">
                        🔓 Unlocked
                      </span>
                    )}
                  </div>
                </div>
                <p className="text-foreground/90 line-clamp-2 text-xs italic">{block.content}</p>
                <div className="text-[10px] text-muted-foreground mt-1 flex justify-between">
                  <span>Author: {block.lastAuthorId}</span>
                  <span>Type: {block.blockType}</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Block Editor & Lease Control */}
        <div className="p-3 rounded-lg border border-border bg-background/50 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-foreground">
              Selected: <code className="text-primary">{selectedBlockId}</code>
            </span>
            <div className="flex gap-1.5">
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => onAcquireLease(selectedBlockId)}
                className="px-2 py-1 text-[11px] bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/30 rounded hover:bg-amber-500/20"
              >
                Acquire Lease
              </button>
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => onReleaseLease(selectedBlockId)}
                className="px-2 py-1 text-[11px] bg-muted text-muted-foreground border border-border rounded hover:bg-muted/80"
              >
                Release
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="block-content-edit" className="block text-[11px] text-muted-foreground mb-1">
              Edit Block Content:
            </label>
            <textarea
              id="block-content-edit"
              rows={3}
              value={editDraft}
              onChange={(e) => onChangeEditDraft(e.target.value)}
              placeholder="Draft modified content..."
              className="w-full text-xs p-2 rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label htmlFor="intent-reason-input" className="block text-[11px] text-muted-foreground mb-1">
              Intent Reason (Audit Trace):
            </label>
            <input
              id="intent-reason-input"
              type="text"
              value={intentInput}
              onChange={(e) => onChangeIntentInput(e.target.value)}
              placeholder="e.g., Hardened encryption protocol requirements"
              className="w-full text-xs px-2 py-1 rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <button
            type="button"
            disabled={isProcessing || !editDraft.trim() || !intentInput.trim()}
            onClick={onCommitEdit}
            className="w-full py-1.5 text-xs font-medium text-white bg-primary rounded hover:bg-primary/90 disabled:opacity-50"
          >
            Commit Delta with Intent
          </button>
        </div>
      </div>
    </div>
  );
};

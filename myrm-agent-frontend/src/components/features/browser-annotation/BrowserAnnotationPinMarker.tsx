'use client';

/**
 * [INPUT]
 * ./browserAnnotationTypes (POS: BrowserAnnotationPin)
 * @/lib/utils/classnameUtils (POS: cn helper)
 * lucide-react (POS: MessageSquare, Trash2, Check, X, Tag)
 *
 * [OUTPUT]
 * BrowserAnnotationPinMarker: Interactive numbered pin with highlight bounding box and popover comment editor.
 *
 * [POS]
 * Visual element pin marker for in-app browser annotation overlay.
 */

import React, { useState, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { MessageSquare, Trash2, Check, X, Tag } from 'lucide-react';
import type { BrowserAnnotationPin } from './browserAnnotationTypes';

interface BrowserAnnotationPinMarkerProps {
  pin: BrowserAnnotationPin;
  scaleX: number;
  scaleY: number;
  isActive: boolean;
  onSelectPin: (id: string) => void;
  onUpdateComment: (id: string, comment: string) => void;
  onDeletePin: (id: string) => void;
}

export const BrowserAnnotationPinMarker: React.FC<BrowserAnnotationPinMarkerProps> = ({
  pin,
  scaleX,
  scaleY,
  isActive,
  onSelectPin,
  onUpdateComment,
  onDeletePin,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [commentDraft, setCommentDraft] = useState(pin.comment);

  const left = pin.box.x * scaleX;
  const top = pin.box.y * scaleY;
  const width = Math.max(pin.box.width * scaleX, 12);
  const height = Math.max(pin.box.height * scaleY, 12);

  const handleSave = useCallback(() => {
    onUpdateComment(pin.id, commentDraft.trim());
    setIsEditing(false);
  }, [onUpdateComment, pin.id, commentDraft]);

  const handleCancel = useCallback(() => {
    setCommentDraft(pin.comment);
    setIsEditing(false);
  }, [pin.comment]);

  return (
    <>
      {/* Element Box Highlight */}
      <div
        data-testid={`annotation-box-${pin.id}`}
        className={cn(
          'absolute border-2 pointer-events-none transition-all duration-150',
          isActive
            ? 'border-primary bg-primary/15 shadow-[0_0_12px_rgba(59,130,246,0.35)] z-30'
            : 'border-amber-500/80 bg-amber-500/10 z-20',
        )}
        style={{
          left: `${left}px`,
          top: `${top}px`,
          width: `${width}px`,
          height: `${height}px`,
        }}
      />

      {/* Numbered Pin Badge */}
      <div
        className="absolute z-40"
        style={{
          left: `${left - 12}px`,
          top: `${top - 12}px`,
        }}
      >
        <button
          type="button"
          data-testid={`annotation-pin-${pin.id}`}
          onClick={(e) => {
            e.stopPropagation();
            onSelectPin(pin.id);
            setIsEditing(true);
          }}
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold shadow-md cursor-pointer',
            'transition-transform duration-150 hover:scale-110 active:scale-95',
            isActive
              ? 'bg-primary text-primary-foreground ring-2 ring-primary/40'
              : 'bg-amber-500 text-white hover:bg-amber-600',
          )}
          aria-label={`Annotation pin ${pin.index}`}
        >
          {pin.index}
        </button>

        {/* Comment Popover */}
        {(isActive || isEditing) && (
          <section
            aria-label="Pin annotation details"
            data-testid={`annotation-popover-${pin.id}`}
            className="absolute left-8 top-0 w-72 bg-popover text-popover-foreground rounded-lg shadow-xl border border-border p-3 z-50 animate-in fade-in zoom-in-95 pointer-events-auto"
          >
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-border text-xs">
              <span className="font-semibold flex items-center gap-1.5 text-primary">
                <MessageSquare className="w-3.5 h-3.5" />
                Pin #{pin.index}
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  data-testid={`delete-pin-${pin.id}`}
                  onClick={() => onDeletePin(pin.id)}
                  className="p-1 text-muted-foreground hover:text-destructive rounded transition-colors"
                  aria-label="Delete annotation"
                  title="Delete annotation"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors"
                  aria-label="Close popover"
                  title="Close"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {pin.domMetadata?.cssSelector && (
              <div className="mb-2 px-1.5 py-1 bg-muted/60 rounded text-[11px] font-mono text-muted-foreground truncate flex items-center gap-1">
                <Tag className="w-3 h-3 shrink-0 text-primary/70" />
                <span className="truncate" title={pin.domMetadata.cssSelector}>
                  {pin.domMetadata.cssSelector}
                </span>
              </div>
            )}

            {isEditing ? (
              <div className="space-y-2">
                <textarea
                  data-testid={`annotation-textarea-${pin.id}`}
                  value={commentDraft}
                  onChange={(e) => setCommentDraft(e.target.value)}
                  placeholder="Describe your design tweak or bug fix..."
                  rows={3}
                  className="w-full text-xs p-2 rounded border border-input bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <div className="flex justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground rounded"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    data-testid={`save-comment-${pin.id}`}
                    onClick={handleSave}
                    className="px-2.5 py-1 text-xs bg-primary text-primary-foreground font-medium rounded hover:bg-primary/90 flex items-center gap-1"
                  >
                    <Check className="w-3 h-3" />
                    Save
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="text-left w-full text-xs text-foreground cursor-pointer hover:bg-muted/30 p-1 rounded block"
                onClick={() => setIsEditing(true)}
              >
                {pin.comment ? (
                  <p className="whitespace-pre-wrap">{pin.comment}</p>
                ) : (
                  <span className="text-muted-foreground italic">Click to add comment...</span>
                )}
              </button>
            )}
          </section>
        )}
      </div>
    </>
  );
};

export default React.memo(BrowserAnnotationPinMarker);

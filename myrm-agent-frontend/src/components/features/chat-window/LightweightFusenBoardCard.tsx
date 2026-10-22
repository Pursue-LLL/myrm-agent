import React, { useState, useMemo } from 'react';
import {
  StickyNote,
  AlertCircle,
  CheckCircle2,
  Sparkles,
  Clock,
  Plus,
  X,
  Filter,
  Check,
} from 'lucide-react';
import type {
  FusenCategory,
  FusenNoteItem,
  LightweightFusenBoardCardProps,
} from './fusen/types';
import { INITIAL_FUSEN_NOTES } from './fusen/types';

export const LightweightFusenBoardCard: React.FC<LightweightFusenBoardCardProps> = ({
  sessionId = 'sess-default',
  initialNotes = INITIAL_FUSEN_NOTES,
  onDismiss,
  onNoteResolved,
  onNotePosted,
}) => {
  const [notes, setNotes] = useState<FusenNoteItem[]>(initialNotes);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [includeResolved, setIncludeResolved] = useState<boolean>(false);
  const [showNewModal, setShowNewModal] = useState<boolean>(false);

  // New note form state
  const [newTag, setNewTag] = useState<string>('');
  const [newContent, setNewContent] = useState<string>('');
  const [newCategory, setNewCategory] = useState<FusenCategory>('blocker');

  // Resolution state
  const [resolvingNoteId, setResolvingNoteId] = useState<string | null>(null);
  const [resolutionInput, setResolutionInput] = useState<string>('');

  const activeBlockers = useMemo(() => {
    return notes.filter((n) => n.status === 'active' && n.category === 'blocker');
  }, [notes]);

  const filteredNotes = useMemo(() => {
    return notes.filter((n) => {
      if (categoryFilter !== 'all' && n.category !== categoryFilter) {
        return false;
      }
      if (!includeResolved && n.status !== 'active') {
        return false;
      }
      return true;
    });
  }, [notes, categoryFilter, includeResolved]);

  const handleResolve = (noteId: string) => {
    const updated = notes.map((n) => {
      if (n.noteId === noteId) {
        return {
          ...n,
          status: 'resolved' as const,
          resolutionNote: resolutionInput || 'Resolved by collaborator.',
          updatedAt: Date.now(),
        };
      }
      return n;
    });
    setNotes(updated);
    setResolvingNoteId(null);
    setResolutionInput('');
    if (onNoteResolved) {
      onNoteResolved(noteId);
    }
  };

  const handleCreateNote = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTag.trim()) {
      return;
    }

    const createdNote: FusenNoteItem = {
      noteId: `fusen-${Date.now().toString(36)}`,
      sessionId,
      authorAgentId: 'local-teammate',
      category: newCategory,
      tag: newTag.trim(),
      content: newContent.trim(),
      status: 'active',
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    setNotes([createdNote, ...notes]);
    setNewTag('');
    setNewContent('');
    setShowNewModal(false);
    if (onNotePosted) {
      onNotePosted(createdNote);
    }
  };

  const getCategoryBadgeClass = (category: FusenCategory) => {
    switch (category) {
      case 'blocker': {
        return 'bg-red-500/10 text-red-500 border-red-500/30';
      }
      case 'ready_for_review': {
        return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30';
      }
      case 'cache_hint': {
        return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      }
      case 'in_progress': {
        return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      }
      default: {
        return 'bg-amber-500/10 text-amber-500 border-amber-500/30';
      }
    }
  };

  return (
    <section
      aria-label="Lightweight Fusen Shared State Board"
      className="flex flex-col border rounded-xl bg-card text-card-foreground shadow-sm overflow-hidden my-3 max-w-4xl border-border"
    >
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
        <div className="flex items-center gap-2.5">
          <StickyNote className="w-5 h-5 text-amber-500" />
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              Fusen Shared State Board
              <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-amber-500/10 text-amber-500 border border-amber-500/20">
                {sessionId}
              </span>
            </h3>
            <p className="text-xs text-muted-foreground line-clamp-1">
              Zero-overhead subagent sticky notes & sub-millisecond blocker sync
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {activeBlockers.length > 0 ? (
            <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium bg-red-500/10 text-red-500 border border-red-500/20">
              <AlertCircle className="w-3.5 h-3.5" />
              {activeBlockers.length} Active Blocker{activeBlockers.length > 1 ? 's' : ''}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Swarm Clear
            </span>
          )}
          <button
            type="button"
            onClick={() => {
              setShowNewModal(true);
            }}
            className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Post Fusen
          </button>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Close Fusen board"
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      {/* Filter Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-background text-xs">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Category:</span>
          {(['all', 'blocker', 'ready_for_review', 'cache_hint', 'in_progress'] as const).map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => {
                setCategoryFilter(cat);
              }}
              className={`px-2 py-0.5 rounded capitalize transition-colors ${
                categoryFilter === cat
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {cat.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
          <input
            type="checkbox"
            checked={includeResolved}
            onChange={(e) => {
              setIncludeResolved(e.target.checked);
            }}
            className="rounded border-border"
          />
          Include Resolved
        </label>
      </div>

      {/* Main Sticky-Note Grid Wall */}
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {filteredNotes.length === 0 ? (
          <div className="col-span-full py-8 text-center text-xs text-muted-foreground">
            No active Fusen sticky notes matching filter criteria.
          </div>
        ) : (
          filteredNotes.map((note) => {
            const isBlocker = note.category === 'blocker';
            const isResolved = note.status === 'resolved';

            return (
              <div
                key={note.noteId}
                className={`flex flex-col justify-between p-3 rounded-lg border text-xs transition-shadow shadow-xs ${
                  isResolved
                    ? 'bg-muted/20 border-border opacity-70'
                    : isBlocker
                    ? 'bg-red-500/5 border-red-500/30'
                    : 'bg-card border-border hover:shadow-sm'
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-1">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono border uppercase tracking-wider ${getCategoryBadgeClass(
                        note.category
                      )}`}
                    >
                      {note.category.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(note.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  <div className="font-semibold text-foreground line-clamp-1">{note.tag}</div>
                  {note.content && (
                    <p className="text-muted-foreground line-clamp-3 whitespace-pre-wrap">{note.content}</p>
                  )}
                  {note.authorAgentId && (
                    <div className="text-[10px] text-muted-foreground">Author: {note.authorAgentId}</div>
                  )}

                  {isResolved && note.resolutionNote && (
                    <div className="p-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded text-[11px] text-emerald-400">
                      ✓ {note.resolutionNote}
                    </div>
                  )}
                </div>

                {/* Bottom Action Area */}
                {!isResolved && (
                  <div className="mt-3 pt-2 border-t border-border flex items-center justify-between">
                    {resolvingNoteId === note.noteId ? (
                      <div className="w-full flex items-center gap-1.5">
                        <input
                          type="text"
                          placeholder="Resolution note..."
                          value={resolutionInput}
                          onChange={(e) => {
                            setResolutionInput(e.target.value);
                          }}
                          className="flex-1 px-2 py-1 bg-background border border-border rounded text-[11px] text-foreground"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            handleResolve(note.noteId);
                          }}
                          className="p-1 bg-emerald-500 text-white rounded hover:bg-emerald-600"
                          aria-label="Confirm resolve"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setResolvingNoteId(null);
                          }}
                          className="p-1 bg-muted text-muted-foreground rounded hover:bg-muted/80"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setResolvingNoteId(note.noteId);
                        }}
                        className="text-[11px] text-muted-foreground hover:text-emerald-400 transition-colors flex items-center gap-1"
                      >
                        <CheckCircle2 className="w-3 h-3" />
                        Resolve
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Post Modal Dialog */}
      {showNewModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-xs flex items-center justify-center p-4">
          <form
            onSubmit={handleCreateNote}
            className="bg-card border border-border rounded-xl shadow-lg max-w-md w-full p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-amber-500" />
                Post Lightweight Fusen Sticky Note
              </h4>
              <button
                type="button"
                onClick={() => {
                  setShowNewModal(false);
                }}
                className="p-1 text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-1">
              <label htmlFor="fusen-category-select" className="text-xs font-medium text-foreground">Category</label>
              <select
                id="fusen-category-select"
                value={newCategory}
                onChange={(e) => {
                  setNewCategory(e.target.value as FusenCategory);
                }}
                className="w-full px-2.5 py-1.5 bg-background border border-border rounded-md text-xs text-foreground"
              >
                <option value="blocker">Blocker (Immediate team attention)</option>
                <option value="ready_for_review">Ready for Review (Peer inspection)</option>
                <option value="cache_hint">Cache Hint (Reusable artifact flag)</option>
                <option value="in_progress">In Progress (Active lane flag)</option>
                <option value="custom">Custom Tag</option>
              </select>
            </div>

            <div className="space-y-1">
              <label htmlFor="fusen-tag-input" className="text-xs font-medium text-foreground">Tag</label>
              <input
                id="fusen-tag-input"
                type="text"
                placeholder="e.g. blocked_by: api_gateway_503"
                value={newTag}
                onChange={(e) => {
                  setNewTag(e.target.value);
                }}
                className="w-full px-2.5 py-1.5 bg-background border border-border rounded-md text-xs text-foreground font-mono"
                required
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="fusen-content-textarea" className="text-xs font-medium text-foreground">Content / Details (Optional)</label>
              <textarea
                id="fusen-content-textarea"
                placeholder="Provide minimal micro-context for collaborative teammates..."
                value={newContent}
                onChange={(e) => {
                  setNewContent(e.target.value);
                }}
                rows={3}
                className="w-full px-2.5 py-1.5 bg-background border border-border rounded-md text-xs text-foreground resize-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowNewModal(false);
                }}
                className="px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted rounded-md"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-3.5 py-1.5 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 rounded-md"
              >
                Post Sticky Note
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
};

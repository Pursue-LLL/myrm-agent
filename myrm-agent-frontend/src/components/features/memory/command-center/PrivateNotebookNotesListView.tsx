'use client';

/**
 * [INPUT]
 * @/services/memory/privateNotebook::NoteMetadataDTO, NoteEntryDTO
 *
 * [OUTPUT]
 * PrivateNotebookNotesListView: Subview component rendering notes list, inspector, and rectification dialog.
 *
 * [POS]
 * Subcomponent for Item 89 (Transparent Inspectable Model Private Notebook Suite).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { BookOpen, Edit3, Trash2, Calendar, FileText, Check } from 'lucide-react';
import type { NoteMetadataDTO, NoteEntryDTO } from '@/services/memory/privateNotebook';

interface PrivateNotebookNotesListViewProps {
  notes: NoteMetadataDTO[];
  selectedNote: NoteEntryDTO | null;
  isLoadingNote: boolean;
  onSelectNote: (title: string) => void;
  onRewriteNote: (title: string, newContent: string) => Promise<void>;
  onDeleteNote: (title: string) => Promise<void>;
}

export function PrivateNotebookNotesListView({
  notes,
  selectedNote,
  isLoadingNote,
  onSelectNote,
  onRewriteNote,
  onDeleteNote,
}: PrivateNotebookNotesListViewProps): React.JSX.Element {
  const [editingContent, setEditingContent] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const handleStartEdit = (note: NoteEntryDTO) => {
    setEditingContent(note.content);
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedNote) return;
    setIsSaving(true);
    try {
      await onRewriteNote(selectedNote.title, editingContent);
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="private-notebook-notes-list-view">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Notes list index */}
        <div className="rounded-md border border-border/70 p-2.5 bg-card space-y-2">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <BookOpen className="h-3.5 w-3.5 text-primary" />
              <span>本地透明笔记索引 ({notes.length})</span>
            </span>
            <span className="text-[10px] text-muted-foreground">存储于 .myrm/agent_notes/</span>
          </div>

          <div className="space-y-1.5 max-h-56 overflow-y-auto">
            {notes.length > 0 ? (
              notes.map((n) => (
                <button
                  type="button"
                  key={n.title}
                  onClick={() => onSelectNote(n.title)}
                  className={`w-full text-left rounded border p-2 transition-colors flex flex-col gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    selectedNote?.title === n.title
                      ? 'border-primary/60 bg-primary/10'
                      : 'border-border/50 bg-background hover:bg-muted/50'
                  }`}
                  data-testid={`note-item-${n.title}`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-medium text-foreground truncate">{n.title}</span>
                    <Badge variant="outline" className="text-[9px] py-0 px-1 text-primary shrink-0">
                      {n.char_count} 字符
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span className="flex items-center gap-0.5">
                      <FileText className="h-2.5 w-2.5" />
                      {n.line_count} 行
                    </span>
                    <span className="flex items-center gap-0.5">
                      <Calendar className="h-2.5 w-2.5" />
                      {n.updated_at ? n.updated_at.slice(0, 16).replace('T', ' ') : '刚刚'}
                    </span>
                  </div>
                  {n.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {n.tags.map((tag) => (
                        <span key={tag} className="text-[9px] bg-muted px-1 rounded text-muted-foreground">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              ))
            ) : (
              <div className="text-center py-6 text-muted-foreground text-xs">
                暂无透明私有笔记，可通过上方快速操作追加或由模型自动维护
              </div>
            )}
          </div>
        </div>

        {/* Selected note reader and human rectification console */}
        <div className="rounded-md border border-border/70 p-2.5 bg-card flex flex-col justify-between space-y-2">
          {selectedNote ? (
            <div className="space-y-2 flex-1 flex flex-col">
              <div className="flex items-center justify-between gap-2 border-b border-border/40 pb-1.5">
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-foreground truncate flex items-center gap-1">
                    <span>{selectedNote.title}.md</span>
                    <Badge variant="secondary" className="text-[9px] py-0 px-1">
                      可检视
                    </Badge>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {!isEditing ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 text-[10px] px-2 gap-1"
                      onClick={() => handleStartEdit(selectedNote)}
                      data-testid="edit-note-btn"
                    >
                      <Edit3 className="h-3 w-3" />
                      人工纠偏
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="default"
                      className="h-6 text-[10px] px-2 gap-1"
                      onClick={handleSaveEdit}
                      disabled={isSaving}
                      data-testid="save-note-btn"
                    >
                      <Check className="h-3 w-3" />
                      {isSaving ? '保存中...' : '提交覆写'}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 text-[10px] px-1.5 text-destructive hover:bg-destructive/10"
                    onClick={() => onDeleteNote(selectedNote.title)}
                    data-testid="delete-note-btn"
                    aria-label={`删除笔记 ${selectedNote.title}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {isEditing ? (
                <div className="space-y-1 flex-1 flex flex-col">
                  <label htmlFor="rectification-content" className="text-[10px] text-muted-foreground">
                    Markdown 修正正文 (原子覆盖):
                  </label>
                  <textarea
                    id="rectification-content"
                    value={editingContent}
                    onChange={(e) => setEditingContent(e.target.value)}
                    rows={6}
                    className="w-full flex-1 rounded border border-input bg-background p-2 text-xs font-mono focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    data-testid="rectification-textarea"
                  />
                </div>
              ) : (
                <div className="flex-1 max-h-52 overflow-y-auto rounded bg-muted/40 p-2 text-xs font-mono text-foreground whitespace-pre-wrap">
                  {selectedNote.content}
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-4 text-muted-foreground text-xs">
              {isLoadingNote ? '正在读取笔记正文...' : '点击左侧笔记条目以进行透明检视或人工纠偏'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

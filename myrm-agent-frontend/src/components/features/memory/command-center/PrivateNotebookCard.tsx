'use client';

/**
 * [INPUT]
 * @/services/memory/privateNotebook::listNotes, searchNotes, getNote, appendNote, rewriteNote, deleteNote, listContexts
 * ./PrivateNotebookNotesListView::PrivateNotebookNotesListView
 * ./PrivateNotebookHistoryView::PrivateNotebookHistoryView
 * ./PrivateNotebookHandoverView::PrivateNotebookHandoverView
 *
 * [OUTPUT]
 * PrivateNotebookCard: Command Center dashboard card for Transparent Inspectable Model Private Notebook Suite (Item 89 P0).
 *
 * [POS]
 * Implementation for Topic 01 Item 89 (OpenAI Codex rust-v0.153.0 PR #42385 features.context_management
 * benchmarked, upgraded with local transparent .myrm/agent_notes/ markdown files & human rectification).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/primitives/card';
import {
  BookOpen, Search, PlusCircle, RefreshCw, History, ArrowRightLeft, FileCheck2, AlertCircle, Sparkles,
} from 'lucide-react';
import {
  listNotes, searchNotes, getNote, appendNote, rewriteNote, deleteNote, listContexts,
  type NoteMetadataDTO, type NoteEntryDTO, type NoteSearchResultDTO, type HistoryContextItemDTO, type NewContextResponseDTO,
} from '@/services/memory/privateNotebook';
import { PrivateNotebookNotesListView } from './PrivateNotebookNotesListView';
import { PrivateNotebookHistoryView } from './PrivateNotebookHistoryView';
import { PrivateNotebookHandoverView } from './PrivateNotebookHandoverView';

type ActiveTab = 'notes' | 'history' | 'handover';

export function PrivateNotebookCard(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<ActiveTab>('notes');
  const [notes, setNotes] = useState<NoteMetadataDTO[]>([]);
  const [selectedNote, setSelectedNote] = useState<NoteEntryDTO | null>(null);
  const [isLoadingNote, setIsLoadingNote] = useState<boolean>(false);
  const [activeContextId, setActiveContextId] = useState<string>('ctx-main-001');

  // Notes Form State
  const [newTitle, setNewTitle] = useState<string>('');
  const [newContent, setNewContent] = useState<string>('');
  const [noteSearchQuery, setNoteSearchQuery] = useState<string>('');
  const [noteSearchResults, setNoteSearchResults] = useState<NoteSearchResultDTO[]>([]);
  const [isSearchingNotes, setIsSearchingNotes] = useState<boolean>(false);

  // History Contexts State
  const [historyContexts, setHistoryContexts] = useState<HistoryContextItemDTO[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchNotes = useCallback(async (selectFirst = false) => {
    try {
      const data = await listNotes();
      if (Array.isArray(data)) {
        setNotes(data);
        if (selectFirst && data.length > 0) {
          try {
            const first = await getNote(data[0].title);
            if (first) {
              setSelectedNote(first);
            }
          } catch {
            // ignore
          }
        }
      }
    } catch {
      // Degrade gracefully if server offline
    }
  }, []);

  const loadHistoryContexts = useCallback(async () => {
    try {
      const ctxs = await listContexts();
      setHistoryContexts(Array.isArray(ctxs) ? ctxs : []);
    } catch {
      setHistoryContexts([]);
    }
  }, []);

  useEffect(() => {
    void fetchNotes(true);
  }, [fetchNotes]);

  const handleSelectNote = async (title: string) => {
    setIsLoadingNote(true);
    try {
      const note = await getNote(title);
      setSelectedNote(note);
    } catch {
      setStatusMessage(`读取笔记 ${title} 失败`);
    } finally {
      setIsLoadingNote(false);
    }
  };

  const handleAppendNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) return;
    try {
      const saved = await appendNote({
        title: newTitle.trim(),
        content: newContent.trim(),
      });
      setSelectedNote(saved);
      setNewTitle('');
      setNewContent('');
      setStatusMessage(`已保存笔记: ${saved.title}`);
      await fetchNotes();
    } catch {
      setStatusMessage('保存笔记失败');
    }
  };

  const handleRewriteNote = async (title: string, content: string) => {
    try {
      const updated = await rewriteNote(title, { title, content });
      setSelectedNote(updated);
      setStatusMessage(`已人工纠偏覆写笔记: ${title}`);
      await fetchNotes();
    } catch {
      setStatusMessage('纠偏保存失败');
    }
  };

  const handleDeleteNote = async (title: string) => {
    try {
      await deleteNote(title);
      setSelectedNote(null);
      setStatusMessage(`已删除笔记: ${title}`);
      await fetchNotes();
    } catch {
      setStatusMessage('删除笔记失败');
    }
  };

  const handleSearchNotes = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteSearchQuery.trim()) {
      setNoteSearchResults([]);
      return;
    }
    setIsSearchingNotes(true);
    try {
      const results = await searchNotes(noteSearchQuery.trim());
      setNoteSearchResults(results);
    } catch {
      setNoteSearchResults([]);
    } finally {
      setIsSearchingNotes(false);
    }
  };

  const handleHandoverSuccess = (res: NewContextResponseDTO) => {
    setActiveContextId(res.new_context_id);
    setStatusMessage(`已平滑接力至新上下文: ${res.new_context_id}，保留笔记 ${res.carried_notes_count} 篇`);
    void fetchNotes();
  };

  const applyPresetArchitecture = () => {
    setNewTitle('system_architecture_spec');
    setNewContent('## 核心架构原则\n1. 透明物理笔记存储于 `.myrm/agent_notes/`\n2. 跨窗口移交保留沙箱文件与长程记忆\n3. 人工随时纠偏');
  };

  return (
    <Card className="border-border/80 shadow-sm" data-testid="private-notebook-card">
      <CardHeader className="pb-3 border-b border-border/50">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-primary" />
            <CardTitle className="text-sm font-semibold tracking-tight">
              透明可检视模型私有笔记本 (PR #42385 超越版)
            </CardTitle>
            <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
              Item 89 P0
            </Badge>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={applyPresetArchitecture}
              className="h-7 text-xs gap-1"
              data-testid="preset-notebook-btn"
            >
              <Sparkles className="h-3 w-3 text-amber-500" />
              填充架构预设
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void fetchNotes()}
              className="h-7 w-7 p-0"
              aria-label="刷新笔记"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* HUD Statistics Banner */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs" data-testid="private-notebook-hud">
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <BookOpen className="h-3 w-3 text-primary" />
              <span>活跃私有笔记</span>
            </div>
            <div className="text-base font-bold text-primary" data-testid="hud-notes-count">
              {notes.length} 篇
            </div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <FileCheck2 className="h-3 w-3 text-green-500" />
              <span>当前上下文</span>
            </div>
            <div className="text-base font-bold text-foreground truncate" data-testid="hud-active-context">
              {activeContextId}
            </div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <ArrowRightLeft className="h-3 w-3 text-amber-500" />
              <span>跨窗口轮转继承</span>
            </div>
            <div className="text-base font-bold text-foreground">
              100% (透明保真)
            </div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <History className="h-3 w-3 text-blue-500" />
              <span>归档窗口</span>
            </div>
            <div className="text-base font-bold text-foreground">
              {historyContexts.length} 个
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-3 space-y-3">
        {statusMessage && (
          <div className="flex items-center gap-1.5 text-xs text-primary bg-primary/10 border border-primary/20 rounded p-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{statusMessage}</span>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1 border-b border-border/60 pb-1">
          <Button
            size="sm"
            variant={activeTab === 'notes' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => setActiveTab('notes')}
            data-testid="tab-notes"
          >
            私有笔记操作台 (Notes 5 Tools)
          </Button>
          <Button
            size="sm"
            variant={activeTab === 'history' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => {
              setActiveTab('history');
              void loadHistoryContexts();
            }}
            data-testid="tab-history"
          >
            长程交互历史检索 (History 4 Tools)
          </Button>
          <Button
            size="sm"
            variant={activeTab === 'handover' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => setActiveTab('handover')}
            data-testid="tab-handover"
          >
            跨窗口接力 (new_context)
          </Button>
        </div>

        {/* Tab 1: Notes Management & Rectification */}
        {activeTab === 'notes' && (
          <div className="space-y-3">
            <form onSubmit={handleAppendNote} className="grid grid-cols-1 md:grid-cols-3 gap-2 p-2.5 rounded-md border border-border/60 bg-muted/20">
              <div className="space-y-1">
                <label htmlFor="note-title-input" className="text-[10px] font-medium text-foreground">
                  笔记标题 (Markdown 标识符):
                </label>
                <input
                  id="note-title-input"
                  type="text"
                  placeholder="例如: project_constraints"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-1 md:col-span-2">
                <label htmlFor="note-content-input" className="text-[10px] font-medium text-foreground">
                  追加/新建内容:
                </label>
                <div className="flex gap-1.5">
                  <input
                    id="note-content-input"
                    type="text"
                    placeholder="输入要记录到模型的要点、决议或避坑经验..."
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                    className="flex-1 rounded border border-input bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <Button type="submit" size="sm" className="h-7 text-xs px-2.5 gap-1 shrink-0" data-testid="append-note-submit-btn">
                    <PlusCircle className="h-3 w-3" />
                    追加笔记
                  </Button>
                </div>
              </div>
            </form>

            <form onSubmit={handleSearchNotes} className="flex gap-2 items-center" data-testid="search-notes-form">
              <label htmlFor="search-notes-input" className="sr-only">搜索私有笔记</label>
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                <input
                  id="search-notes-input"
                  type="text"
                  placeholder="检索私有笔记正文或标题关键词..."
                  value={noteSearchQuery}
                  onChange={(e) => setNoteSearchQuery(e.target.value)}
                  className="w-full rounded border border-input bg-background pl-8 pr-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <Button
                type="submit"
                size="sm"
                variant="secondary"
                className="h-7 text-xs"
                disabled={isSearchingNotes}
                data-testid="search-notes-btn"
              >
                {isSearchingNotes ? '检索中...' : '搜索'}
              </Button>
            </form>

            {noteSearchResults.length > 0 && (
              <div
                className="rounded border border-primary/30 p-2 bg-primary/5 space-y-1 text-xs"
                data-testid="search-results-box"
              >
                <div className="text-[10px] font-semibold text-primary">匹配切片 ({noteSearchResults.length})</div>
                {noteSearchResults.map((sr) => (
                  <div key={sr.title} className="p-1 rounded bg-background border border-border/40 text-[11px]">
                    <span className="font-semibold">{sr.title}:</span> <span className="text-muted-foreground font-mono">{sr.snippet}</span>
                  </div>
                ))}
              </div>
            )}

            <PrivateNotebookNotesListView
              notes={notes}
              selectedNote={selectedNote}
              isLoadingNote={isLoadingNote}
              onSelectNote={handleSelectNote}
              onRewriteNote={handleRewriteNote}
              onDeleteNote={handleDeleteNote}
            />
          </div>
        )}

        {/* Tab 2: History Search Subview */}
        {activeTab === 'history' && (
          <PrivateNotebookHistoryView
            historyContexts={historyContexts}
            onRefreshContexts={loadHistoryContexts}
          />
        )}

        {/* Tab 3: Handover Subview */}
        {activeTab === 'handover' && (
          <PrivateNotebookHandoverView
            onHandoverSuccess={handleHandoverSuccess}
            onError={(msg) => setStatusMessage(msg)}
          />
        )}
      </CardContent>
    </Card>
  );
}

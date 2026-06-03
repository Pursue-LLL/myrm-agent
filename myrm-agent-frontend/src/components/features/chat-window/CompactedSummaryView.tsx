import React, { useState } from 'react';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { FileText, Edit2, Save, X, History } from 'lucide-react';
import { getChatArchive, updateCompactionSummary } from '@/services/chat';
import type { Message } from '@/store/chat/types';
import { format } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

const markdownLinkComponents = {
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
    const isExternal = href && /^https?:\/\//.test(href);
    if (isExternal) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline hover:text-primary/80"
        >
          {children}
        </a>
      );
    }
    return <a href={href}>{children}</a>;
  },
};

export const CompactedSummaryView = () => {
  const { chatId, compactedSummary, setCompactedSummary } = useChatStore(
    useShallow((state) => ({
      chatId: state.chatId,
      compactedSummary: state.compactedSummary,
      setCompactedSummary: state.setCompactedSummary,
    })),
  );

  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const [archiveMessages, setArchiveMessages] = useState<Message[]>([]);
  const [isLoadingArchive, setIsLoadingArchive] = useState(false);

  if (!compactedSummary) return null;

  const handleEdit = () => {
    setEditValue(compactedSummary);
    setIsEditing(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
  };

  const handleSave = async () => {
    if (!chatId) return;
    setIsSaving(true);
    try {
      await updateCompactionSummary(chatId, editValue);
      setCompactedSummary(editValue);
      setIsEditing(false);
    } catch (err) {
      console.error('Failed to save summary:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleViewArchive = async () => {
    setIsArchiveOpen(true);
    if (!chatId || archiveMessages.length > 0) return;

    setIsLoadingArchive(true);
    try {
      const res = await getChatArchive(chatId);
      setArchiveMessages(res.messages || []);
    } catch (err) {
      console.error('Failed to fetch archive:', err);
    } finally {
      setIsLoadingArchive(false);
    }
  };

  return (
    <div className="w-full flex flex-col items-center my-6 max-w-5xl mx-auto px-4 md:px-0">
      {/* Fold Line UI */}
      <div className="flex items-center w-full my-4 opacity-50">
        <div className="flex-1 h-px bg-border" />
        <span
          role="button"
          tabIndex={0}
          className="px-4 text-xs font-medium text-muted-foreground flex items-center gap-1.5 cursor-pointer hover:text-primary transition-colors"
          onClick={handleViewArchive}
          onKeyDown={(e) => e.key === 'Enter' && handleViewArchive()}
        >
          <History className="w-3.5 h-3.5" />
          上下文已压缩 Context Folded
        </span>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* Editable Glass Box */}
      <div className="w-full relative group rounded-xl border border-primary/20 bg-primary/5 p-4 backdrop-blur-sm transition-all hover:border-primary/40">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-primary">
            <FileText className="w-4 h-4" />
            AI 记忆胶囊 (Structured Summary)
          </div>
          <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            {!isEditing ? (
              <button
                onClick={handleEdit}
                className="text-xs flex items-center gap-1 bg-background hover:bg-muted text-foreground px-2 py-1 rounded-full border"
              >
                <Edit2 className="w-3 h-3" /> 编辑记忆
              </button>
            ) : (
              <>
                <button
                  onClick={handleCancel}
                  className="text-xs flex items-center gap-1 bg-background hover:bg-muted text-foreground px-2 py-1 rounded-full border"
                  disabled={isSaving}
                >
                  <X className="w-3 h-3" /> 取消
                </button>
                <button
                  onClick={handleSave}
                  className="text-xs flex items-center gap-1 bg-primary hover:bg-primary/90 text-primary-foreground px-2 py-1 rounded-full"
                  disabled={isSaving}
                >
                  {isSaving ? (
                    <div className="w-3 h-3 animate-spin rounded-full border-2 border-background border-t-transparent" />
                  ) : (
                    <Save className="w-3 h-3" />
                  )}
                  保存
                </button>
              </>
            )}
          </div>
        </div>

        {isEditing ? (
          <textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="w-full min-h-[200px] text-sm bg-background border rounded-lg p-3 focus:outline-none focus:ring-1 focus:ring-primary font-mono resize-y"
          />
        ) : (
          <div className="prose dark:prose-invert prose-sm max-w-none break-words text-sm text-foreground/80 whitespace-pre-wrap max-h-[300px] overflow-y-auto scrollbar-thin">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={markdownLinkComponents}
            >
              {compactedSummary}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {/* Archive Modal (Simplified) */}
      {isArchiveOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 md:p-8">
          <div className="bg-background border shadow-xl rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
            <div className="p-4 border-b flex items-center justify-between bg-muted/30">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <History className="w-5 h-5" />
                折叠的历史消息 Archive
              </h2>
              <button onClick={() => setIsArchiveOpen(false)} className="p-2 hover:bg-muted rounded-full">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-6">
              {isLoadingArchive ? (
                <div className="flex justify-center p-8">
                  <div className="w-8 h-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                </div>
              ) : archiveMessages.length === 0 ? (
                <div className="text-center text-muted-foreground p-8">暂无归档数据 No archived messages found.</div>
              ) : (
                archiveMessages.map((msg, idx) => (
                  <div
                    key={msg.messageId || idx}
                    className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                  >
                    <div className="text-xs text-muted-foreground mb-1">
                      {msg.role === 'user' ? 'You' : 'AI'} •{' '}
                      {msg.createdAt ? format(new Date(msg.createdAt), 'yyyy-MM-dd HH:mm:ss') : ''}
                    </div>
                    <div
                      className={`prose dark:prose-invert prose-sm max-w-none break-words max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                        msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
                      }`}
                    >
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={markdownLinkComponents}
                      >
                        {msg.content || ''}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

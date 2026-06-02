'use client';

/**
 * Workspace file content preview and editor
 *
 * [INPUT]
 * - file: FileEntry to preview/edit
 * - workspace: Workspace root path for API calls
 *
 * [OUTPUT]
 * - WorkspaceFilePreview: Full-height panel showing file content with
 *   line numbers, edit mode toggle, and Ctrl+S save.
 *
 * [POS]
 * File content preview/editor for the workspace browser. Fetches file
 * content via /browse/content API and renders with line numbers. Supports
 * inline editing with Ctrl+S / Cmd+S keyboard save shortcut.
 */

import React, { memo, useEffect, useState, useCallback, useRef } from 'react';
import { X, Download, RefreshCw, FileText, AlertTriangle, Pencil, Save, Eye } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import { CLIFileIcon } from '@/components/ui/cli-visualization/CLIFileIcon';
import {
  fetchWorkspaceFileContent,
  getWorkspaceFileContentUrl,
  saveWorkspaceFileContent,
  type FileEntry,
} from '@/services/chat';

interface WorkspaceFilePreviewProps {
  file: FileEntry;
  workspace: string;
  onClose: () => void;
  className?: string;
}

function getLanguage(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    tsx: 'tsx',
    jsx: 'jsx',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    toml: 'toml',
    xml: 'xml',
    html: 'html',
    htm: 'html',
    css: 'css',
    scss: 'scss',
    less: 'less',
    md: 'markdown',
    sql: 'sql',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    rs: 'rust',
    go: 'go',
    java: 'java',
    kt: 'kotlin',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    hpp: 'cpp',
    cs: 'csharp',
    rb: 'ruby',
    php: 'php',
    swift: 'swift',
    r: 'r',
    lua: 'lua',
    csv: 'csv',
    svg: 'xml',
  };
  return map[ext] || 'plaintext';
}

function formatBytes(bytes: number | null): string {
  if (bytes === null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Line-numbered code viewer
// ---------------------------------------------------------------------------

const LineNumberedCode: React.FC<{ content: string; language: string }> = memo(({ content, language }) => {
  const lines = content.split('\n');

  return (
    <div className="flex text-xs font-mono leading-relaxed">
      <div className="select-none text-right pr-3 pl-2 text-muted-foreground/50 border-r border-border/30 shrink-0 sticky left-0 bg-background">
        {lines.map((_, i) => (
          <div key={i} className="h-5">
            {i + 1}
          </div>
        ))}
      </div>
      <pre className="pl-3 pr-3 flex-1 whitespace-pre-wrap break-words text-foreground overflow-x-auto">
        <code data-language={language}>{content}</code>
      </pre>
    </div>
  );
});
LineNumberedCode.displayName = 'LineNumberedCode';

// ---------------------------------------------------------------------------
// Line-numbered editor
// ---------------------------------------------------------------------------

const LineNumberedEditor: React.FC<{
  content: string;
  onChange: (value: string) => void;
}> = memo(({ content, onChange }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineCountRef = useRef<HTMLDivElement>(null);
  const lines = content.split('\n');

  const syncScroll = useCallback(() => {
    if (textareaRef.current && lineCountRef.current) {
      lineCountRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  }, []);

  return (
    <div className="flex text-xs font-mono leading-relaxed h-full">
      <div
        ref={lineCountRef}
        className="select-none text-right pr-3 pl-2 text-muted-foreground/50 border-r border-border/30 shrink-0 overflow-hidden bg-background"
      >
        {lines.map((_, i) => (
          <div key={i} className="h-5">
            {i + 1}
          </div>
        ))}
      </div>
      <textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
        className="flex-1 pl-3 pr-3 bg-transparent text-foreground outline-none resize-none leading-relaxed whitespace-pre overflow-auto"
        spellCheck={false}
      />
    </div>
  );
});
LineNumberedEditor.displayName = 'LineNumberedEditor';

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const WorkspaceFilePreview: React.FC<WorkspaceFilePreviewProps> = memo(
  ({ file, workspace, onClose, className }) => {
    const t = useTranslations('workspace');
    const [content, setContent] = useState<string | null>(null);
    const [editContent, setEditContent] = useState<string>('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editing, setEditing] = useState(false);
    const [dirty, setDirty] = useState(false);

    const loadContent = useCallback(async () => {
      setLoading(true);
      setError(null);
      try {
        const text = await fetchWorkspaceFileContent(file.path, workspace);
        setContent(text);
        setEditContent(text);
        setDirty(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load file');
      } finally {
        setLoading(false);
      }
    }, [file.path, workspace]);

    useEffect(() => {
      loadContent();
      setEditing(false);
    }, [loadContent]);

    const handleSave = useCallback(async () => {
      if (!dirty || saving) return;
      setSaving(true);
      try {
        await saveWorkspaceFileContent(workspace, file.path, editContent);
        setContent(editContent);
        setDirty(false);
        toast.success(t('saveSuccess'));
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('saveFailed'));
      } finally {
        setSaving(false);
      }
    }, [workspace, file.path, editContent, dirty, saving, t]);

    const handleEditChange = useCallback((value: string) => {
      setEditContent(value);
      setDirty(true);
    }, []);

    const toggleEdit = useCallback(() => {
      if (editing && dirty) {
        if (!window.confirm(t('discardConfirm'))) return;
        setEditContent(content || '');
        setDirty(false);
      }
      setEditing((prev) => !prev);
    }, [editing, dirty, content, t]);

    // Ctrl+S / Cmd+S
    useEffect(() => {
      const handler = (e: globalThis.KeyboardEvent) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 's' && editing) {
          e.preventDefault();
          handleSave();
        }
      };
      window.addEventListener('keydown', handler);
      return () => window.removeEventListener('keydown', handler);
    }, [editing, handleSave]);

    const handleDownload = useCallback(() => {
      const url = getWorkspaceFileContentUrl(file.path, workspace, true);
      window.open(url, '_blank', 'noopener,noreferrer');
    }, [file.path, workspace]);

    const handleClose = useCallback(() => {
      if (editing && dirty && !window.confirm(t('discardConfirm'))) return;
      onClose();
    }, [editing, dirty, onClose, t]);

    const language = getLanguage(file.name);

    return (
      <div className={cn('flex flex-col h-full bg-background', className)}>
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <CLIFileIcon filename={file.name} className="shrink-0" />
            <span className="text-sm font-medium truncate" title={file.path}>
              {file.name}
            </span>
            {dirty && <span className="text-xs text-amber-500 shrink-0">{t('unsaved')}</span>}
            {file.size !== null && !dirty && (
              <span className="text-xs text-muted-foreground shrink-0">{formatBytes(file.size)}</span>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {content !== null && !loading && (
              <button
                onClick={toggleEdit}
                className={cn('p-1 rounded hover:bg-muted transition-colors', editing && 'bg-muted')}
                title={editing ? t('viewMode') : t('editMode')}
              >
                {editing ? (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Pencil className="h-4 w-4 text-muted-foreground" />
                )}
              </button>
            )}
            {editing && dirty && (
              <button
                onClick={handleSave}
                disabled={saving}
                className="p-1 rounded hover:bg-muted transition-colors"
                title={`${t('save')} (Ctrl+S)`}
              >
                <Save className={cn('h-4 w-4', saving ? 'animate-spin text-muted-foreground' : 'text-primary')} />
              </button>
            )}
            <button
              onClick={handleDownload}
              className="p-1 rounded hover:bg-muted transition-colors"
              title={t('download')}
            >
              <Download className="h-4 w-4 text-muted-foreground" />
            </button>
            <button onClick={handleClose} className="p-1 rounded hover:bg-muted transition-colors" title={t('close')}>
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto py-2">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full px-4 text-muted-foreground">
              <AlertTriangle className="h-6 w-6 mb-2 text-destructive" />
              <span className="text-sm text-center">{error}</span>
            </div>
          ) : content !== null ? (
            editing ? (
              <LineNumberedEditor content={editContent} onChange={handleEditChange} />
            ) : (
              <LineNumberedCode content={content} language={language} />
            )
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <FileText className="h-8 w-8 mb-2" />
              <span className="text-sm">{t('noContent')}</span>
            </div>
          )}
        </div>
      </div>
    );
  },
);

WorkspaceFilePreview.displayName = 'WorkspaceFilePreview';

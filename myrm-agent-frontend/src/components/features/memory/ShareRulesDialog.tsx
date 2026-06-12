'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { Loader2, Copy, Download, Eye, Check } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { cn } from '@/lib/utils/classnameUtils';
import { previewRulesSafe, exportRulesSafe, type SafeRulePreviewItem } from '@/services/memory';
import { toast } from '@/hooks/useToast';

interface ShareRulesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const ShareRulesDialog = memo(function ShareRulesDialog({ open, onOpenChange }: ShareRulesDialogProps) {
  const [previews, setPreviews] = useState<SafeRulePreviewItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [format, setFormat] = useState<'markdown' | 'json'>('markdown');
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) {
      setPreviews([]);
      setSelectedIds(new Set());
      setPreviewContent(null);
      return;
    }
    const load = async () => {
      setIsLoading(true);
      try {
        const items = await previewRulesSafe({ format });
        setPreviews(items);
        setSelectedIds(new Set(items.map((i) => i.id)));
      } catch {
        toast({ title: 'Failed to load rules', variant: 'destructive' });
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [open, format]);

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === previews.length) return new Set();
      return new Set(previews.map((i) => i.id));
    });
  }, [previews]);

  const handlePreview = useCallback((item: SafeRulePreviewItem) => {
    setPreviewContent((prev) => prev === item.rendered ? null : item.rendered);
  }, []);

  const handleExport = useCallback(async () => {
    if (selectedIds.size === 0) {
      toast({ title: 'Please select at least one rule', variant: 'destructive' });
      return;
    }
    setIsExporting(true);
    try {
      await exportRulesSafe({ ruleIds: Array.from(selectedIds), format });
      toast({ title: `Exported ${selectedIds.size} rules successfully` });
    } catch {
      toast({ title: 'Export failed', variant: 'destructive' });
    } finally {
      setIsExporting(false);
    }
  }, [selectedIds, format]);

  const handleCopyAll = useCallback(async () => {
    const selected = previews.filter((p) => selectedIds.has(p.id));
    const text = selected.map((s) => s.rendered).join('\n\n---\n\n');
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast({ title: `Copied ${selected.length} rules to clipboard` });
  }, [previews, selectedIds]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] sm:max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>Share Rules Safely</span>
            <span className="text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 px-2 py-0.5 rounded-full">
              Privacy Protected
            </span>
          </DialogTitle>
          <DialogDescription>
            Export your AI-learned rules with automatic path anonymization and credential redaction.
            Safe to share publicly or with your team.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-3 py-2 border-b">
          <button
            onClick={toggleAll}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {selectedIds.size === previews.length ? 'Deselect All' : 'Select All'}
          </button>
          <span className="text-xs text-muted-foreground">
            {selectedIds.size}/{previews.length} selected
          </span>
          <div className="ml-auto flex gap-1">
            <button
              onClick={() => setFormat('markdown')}
              className={cn(
                'text-xs px-2 py-1 rounded transition-colors',
                format === 'markdown' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-accent',
              )}
            >
              Markdown
            </button>
            <button
              onClick={() => setFormat('json')}
              className={cn(
                'text-xs px-2 py-1 rounded transition-colors',
                format === 'json' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-accent',
              )}
            >
              JSON
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto space-y-1 py-2 min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : previews.length === 0 ? (
            <div className="text-center text-sm text-muted-foreground py-8">
              No procedural rules found. Rules are automatically learned from your conversations.
            </div>
          ) : (
            previews.map((item) => (
              <div key={item.id} className="flex items-start gap-2 p-2 rounded-lg hover:bg-accent/50 transition-colors">
                <input
                  type="checkbox"
                  checked={selectedIds.has(item.id)}
                  onChange={() => toggleSelection(item.id)}
                  className="mt-1 rounded border-muted-foreground/30"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{item.content || item.id}</p>
                </div>
                <button
                  onClick={() => handlePreview(item)}
                  className="shrink-0 p-1 rounded hover:bg-accent transition-colors"
                  title="Preview sanitized content"
                >
                  <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </div>
            ))
          )}
        </div>

        {previewContent && (
          <div className="border-t pt-2">
            <pre className="text-xs bg-muted p-3 rounded-lg overflow-auto max-h-40 whitespace-pre-wrap font-mono">
              {previewContent}
            </pre>
          </div>
        )}

        <DialogFooter className="gap-2">
          <button
            onClick={handleCopyAll}
            disabled={selectedIds.size === 0}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
              'border hover:bg-accent',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <button
            onClick={handleExport}
            disabled={isExporting || selectedIds.size === 0}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {isExporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            Download ZIP
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

export default ShareRulesDialog;
